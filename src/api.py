"""FastAPI backend for live what-if re-optimisation and today's forecast.

Phases 1-7 need no server: Python writes static JSON and React reads it. This
server exists for: (1) the interactive what-if feature (Phase 8a) and (2) the
"Today" tab which fetches a live weather forecast, runs the GA, and returns a
predicted battery schedule for the current day.

Run:
  .venv/Scripts/python -m uvicorn src.api:app --port 8000
  (or: .venv/Scripts/python -m src.api)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.env.battery import BatterySpec
from src.env.objective import evaluate
from src.env.simulator import Scenario, build_scenario
from src.explain.decision_facts import extract_day_facts, render_template
from src.optimization.ga_scheduler import decode, run_ga
from src.optimization.rule_based import dispatch as rule_based_dispatch

ROOT = Path(__file__).resolve().parents[1]
EXPLANATION_JSON = ROOT / "frontend" / "public" / "data" / "explanation.json"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (stdlib only, no python-dotenv dependency). Reads
    KEY=VALUE lines from the repo-root .env into os.environ without overriding
    variables already set in the real environment. Lets you keep GROQ_API_KEY
    in a gitignored file instead of exporting it every terminal session.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

# Groq is OpenAI-compatible; the LLM layer is optional. Without GROQ_API_KEY the
# /explain endpoint quietly serves the deterministic template instead, so the
# feature never hard-depends on the network or a key (important for a live demo).
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# A fixed representative summer day (strong solar surplus, so the battery has a
# clear job and slider changes visibly move the result).
REP_DAY = "2020-06-26"
GA_POP = 100
GA_GEN = 200
CAPITAL_PER_KWH = 250.0  # keep capital consistent with capacity as it's varied
C_RATE = 1.0 / 3.0       # power scales with capacity to hold a fixed 0.33C

app = FastAPI(title="Renewable Energy Optimizer — what-if API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175",
                    "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class WhatIfRequest(BaseModel):
    solar_pct: float = Field(0.0, ge=-50, le=50, description="solar output adjustment, %")
    battery_kwh: float = Field(300.0, ge=50, le=1000, description="battery usable capacity, kWh")


def _spec_for(battery_kwh: float) -> BatterySpec:
    return replace(BatterySpec(), capacity_kwh=battery_kwh,
                   max_power_kw=battery_kwh * C_RATE,
                   capital_cost_eur=battery_kwh * CAPITAL_PER_KWH)


def _perturbed(sc: Scenario, solar_pct: float) -> Scenario:
    return replace(sc, solar_kw=sc.solar_kw * (1.0 + solar_pct / 100.0))


def _optimise(sc: Scenario, spec: BatterySpec) -> dict:
    best, _ = run_ga(spec, sc, GA_POP, GA_GEN, seed=42)
    power = decode(best, spec)
    result = evaluate(power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    return {"cost": round(result["total_cost"], 2),
            "battery_kw": [round(float(v), 2) for v in power]}


@app.get("/health")
def health():
    return {"status": "ok", "representative_day": REP_DAY}


@app.post("/whatif")
def whatif(req: WhatIfRequest):
    base_sc = build_scenario(REP_DAY, 24)
    base = _optimise(base_sc, BatterySpec())

    scen = _perturbed(base_sc, req.solar_pct)
    spec = _spec_for(req.battery_kwh)
    new = _optimise(scen, spec)

    delta = new["cost"] - base["cost"]
    denom = abs(base["cost"]) if base["cost"] else 1.0
    delta_pct = round(delta / denom * 100, 1)

    # Explain the schedule the re-optimiser just produced (the perturbed
    # scenario + the new GA power), so the explanation tracks the sliders
    # rather than a fixed pre-computed day. The scenario_change block lets the
    # renderer/LLM open with what changed and its cost effect.
    facts = extract_day_facts(
        hours=[t.hour for t in scen.timestamps],
        solar_kw=scen.solar_kw, wind_kw=scen.wind_kw, load_kw=scen.load_kw,
        price_eur_mwh=scen.price_eur_mwh, battery_kw=new["battery_kw"],
        date=REP_DAY,
    )
    facts["scenario_change"] = {
        "solar_pct": req.solar_pct,
        "battery_kwh": req.battery_kwh,
        "baseline_cost": base["cost"],
        "new_cost": new["cost"],
        "delta": round(delta, 2),
        "delta_pct": delta_pct,
    }

    return {
        "day": REP_DAY,
        "timestamps": [ts.isoformat() for ts in base_sc.timestamps],
        "baseline_cost": base["cost"],
        "new_cost": new["cost"],
        "delta": round(delta, 2),
        "delta_pct": delta_pct,
        "baseline_kw": base["battery_kw"],
        "new_kw": new["battery_kw"],
        "solar_pct": req.solar_pct,
        "battery_kwh": req.battery_kwh,
        "facts": facts,
        "explanation": render_template(facts),
    }


class ExplainRequest(BaseModel):
    # The frontend passes the facts it already loaded from explanation.json; if
    # omitted, we fall back to the exported canonical facts on disk.
    facts: dict | None = None


def _groq_phrase(facts: dict) -> str | None:
    """Ask Groq to rephrase the pre-computed facts into natural prose. Returns
    None (caller falls back to the template) if there's no key or the call
    fails. The model is given ONLY these facts and told to invent nothing --
    it phrases, it does not reason, so it cannot state a decision reason the
    deterministic extractor didn't already verify.
    """
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None

    system = (
        "You rewrite structured facts about a home/microgrid battery's "
        "charge and discharge decisions into ONE short paragraph (3-5 sentences) "
        "for a non-technical reader. Use ONLY the facts provided. Do not invent "
        "or alter any numbers, times, prices, or reasons. If the facts include a "
        "'scenario_change' block, this is a re-optimisation after the user changed "
        "an input — open by explaining what changed and how it affected the cost, "
        "then explain the battery plan. No bullet points, no headings — just the "
        "paragraph."
    )
    body = json.dumps({
        "model": GROQ_MODEL,
        "temperature": 0.3,
        "max_tokens": 320,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Facts (JSON):\n" + json.dumps(facts)},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Groq sits behind Cloudflare, which 403s (error 1010) the default
            # "Python-urllib/x.y" agent; a named agent passes.
            "User-Agent": "renewable-optimizer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
        return payload["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


@app.post("/explain")
def explain(req: ExplainRequest):
    facts = req.facts
    if facts is None and EXPLANATION_JSON.exists():
        facts = json.loads(EXPLANATION_JSON.read_text(encoding="utf-8")).get("facts")
    if not facts:
        return {"source": "none", "explanation": None,
                "error": "No facts provided and no explanation.json on disk."}

    text = _groq_phrase(facts)
    if text:
        return {"source": "llm", "model": GROQ_MODEL, "explanation": text}
    return {"source": "template", "explanation": render_template(facts)}


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BERLIN_LAT, BERLIN_LON = 52.52, 13.41


def _fetch_open_meteo(lat: float = BERLIN_LAT, lon: float = BERLIN_LON,
                       timezone: str = "Europe/Berlin",
                       forecast_days: int = 1) -> dict:
    """Fetch hourly weather forecast from Open-Meteo (up to 16 days).
    Returns {"hours": [...], "solar_w_m2": [...], "wind_m_s": [...], "temperature": [...]}.
    """
    tz_encoded = urllib.parse.quote(timezone, safe="")
    days = max(1, min(16, forecast_days))
    params = (
        f"?latitude={lat}&longitude={lon}"
        "&hourly=shortwave_radiation,windspeed_10m,temperature_2m"
        f"&timezone={tz_encoded}"
        f"&forecast_days={days}"
    )
    req = urllib.request.Request(
        OPEN_METEO_URL + params,
        headers={"User-Agent": "renewable-optimizer/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    hourly = data["hourly"]
    return {
        "hours": hourly["time"],
        "solar_w_m2": hourly["shortwave_radiation"],
        "wind_m_s": hourly["windspeed_10m"],
        "temperature": hourly["temperature_2m"],
    }


def _extract_day_from_weather(weather: dict, target_date: str) -> dict:
    """Extract a single day's 24h data from a multi-day weather response."""
    indices = [i for i, h in enumerate(weather["hours"]) if h.startswith(target_date)]
    if not indices:
        return None
    import math

    def _safe(v):
        return 0.0 if (v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))) else v

    return {
        "hours": [weather["hours"][i] for i in indices],
        "solar_w_m2": [_safe(weather["solar_w_m2"][i]) for i in indices],
        "wind_m_s": [_safe(weather["wind_m_s"][i]) for i in indices],
        "temperature": [_safe(weather["temperature"][i]) for i in indices],
    }


COUNTRY_ELECTRICITY_EUR_MWH = {
    "Germany": 300, "France": 210, "United Kingdom": 280, "Spain": 230,
    "Italy": 250, "Netherlands": 290, "Belgium": 280, "Austria": 250,
    "Switzerland": 210, "Sweden": 180, "Norway": 150, "Denmark": 310,
    "Poland": 180, "Portugal": 220, "Ireland": 290, "Finland": 160,
    "Czech Republic": 210, "Greece": 200,
    "India": 85, "Bangladesh": 70, "Pakistan": 75, "Sri Lanka": 80,
    "Nepal": 65,
    "United States": 160, "Canada": 120, "Mexico": 95,
    "Brazil": 130, "Argentina": 60, "Chile": 140, "Colombia": 80,
    "China": 80, "Japan": 260, "South Korea": 120, "Taiwan": 90,
    "Australia": 250, "New Zealand": 200,
    "South Africa": 100, "Nigeria": 55, "Kenya": 180, "Egypt": 45,
    "Morocco": 120, "Ghana": 65,
    "United Arab Emirates": 80, "Saudi Arabia": 50, "Turkey": 100,
    "Israel": 160, "Russia": 50, "Singapore": 220, "Thailand": 110,
    "Vietnam": 80, "Indonesia": 90, "Philippines": 170, "Malaysia": 70,
}
DEFAULT_PRICE_EUR_MWH = 150.0

TOU_SHAPE = np.array([
    0.60, 0.55, 0.50, 0.50, 0.55, 0.65, 0.85, 1.10,
    1.20, 1.15, 1.10, 1.05, 1.00, 0.95, 0.90, 0.90,
    0.95, 1.10, 1.25, 1.20, 1.10, 1.00, 0.85, 0.70,
])

COMFORT_TEMP = 22.0
COOLING_GAIN_PER_DEG = 0.012
HEATING_GAIN_PER_DEG = 0.010


def _weather_to_scenario(weather: dict, country: str = "Germany") -> tuple[Scenario, dict]:
    """Convert Open-Meteo weather into a 24h Scenario at microgrid scale.
    Adapts electricity price and load profile to the country and climate.
    Returns (scenario, metadata_dict).
    """
    from src.env.simulator import (
        SOLAR_CAPACITY_KW, WIND_CAPACITY_KW, LOAD_PEAK_KW,
    )

    n = min(24, len(weather["hours"]))
    solar_w_m2 = np.array(weather["solar_w_m2"][:n], dtype=float)
    wind_m_s = np.array(weather["wind_m_s"][:n], dtype=float)
    temperature = np.array(weather["temperature"][:n], dtype=float)

    solar_kw = np.clip(solar_w_m2 / 1000.0, 0, 1) * SOLAR_CAPACITY_KW

    cut_in, rated, cut_out = 3.0, 12.0, 25.0
    wind_fraction = np.where(
        wind_m_s < cut_in, 0.0,
        np.where(wind_m_s < rated,
                 ((wind_m_s - cut_in) / (rated - cut_in)) ** 3,
                 np.where(wind_m_s < cut_out, 1.0, 0.0))
    )
    wind_kw = wind_fraction * WIND_CAPACITY_KW

    base_profile = np.array([
        0.55, 0.50, 0.48, 0.47, 0.50, 0.58, 0.72, 0.85,
        0.92, 0.95, 0.97, 1.00, 0.98, 0.95, 0.90, 0.88,
        0.90, 0.95, 1.00, 0.98, 0.92, 0.85, 0.75, 0.62,
    ])[:n]
    hvac_adj = np.where(
        temperature > COMFORT_TEMP,
        (temperature - COMFORT_TEMP) * COOLING_GAIN_PER_DEG,
        np.where(
            temperature < COMFORT_TEMP - 5,
            (COMFORT_TEMP - 5 - temperature) * HEATING_GAIN_PER_DEG,
            0.0,
        ),
    )
    load_base = LOAD_PEAK_KW * 0.6
    load_kw = load_base + (LOAD_PEAK_KW - load_base) * np.clip(base_profile + hvac_adj, 0.3, 1.3)

    avg_price = COUNTRY_ELECTRICITY_EUR_MWH.get(country, DEFAULT_PRICE_EUR_MWH)
    price = avg_price * TOU_SHAPE[:n]

    timestamps = pd.DatetimeIndex(weather["hours"][:n])

    sc = Scenario(
        timestamps=timestamps,
        solar_kw=solar_kw,
        wind_kw=wind_kw,
        load_kw=load_kw,
        price_eur_mwh=price,
    )
    meta = {
        "solar_w_m2": [round(float(v), 1) for v in solar_w_m2],
        "wind_m_s": [round(float(v), 1) for v in wind_m_s],
        "temperature": weather["temperature"][:n],
        "avg_price_eur_mwh": avg_price,
        "country": country,
    }
    return sc, meta


@app.get("/today")
def today_forecast(lat: float = BERLIN_LAT, lon: float = BERLIN_LON,
                   timezone: str = "Europe/Berlin", country: str = "Germany",
                   date: str | None = None):
    """Fetch weather forecast for any location and date (up to 16 days ahead),
    run GA, return predicted battery schedule. If date is omitted, uses today."""
    try:
        tz_now = pd.Timestamp.now(tz=timezone)
    except Exception:
        tz_now = pd.Timestamp.now(tz="UTC")

    today_str = str(tz_now.date())

    if date is not None:
        try:
            target = pd.Timestamp(date).date()
        except Exception:
            return {"error": f"Invalid date format: {date}. Use YYYY-MM-DD."}
        days_ahead = (target - tz_now.date()).days
        if days_ahead < 0:
            return {"error": "Cannot predict past dates. Open-Meteo only provides forecasts."}
        if days_ahead > 15:
            return {"error": "Cannot predict more than 16 days ahead. Open-Meteo forecast limit."}
        forecast_days = days_ahead + 1
        target_date = str(target)
    else:
        forecast_days = 1
        target_date = today_str

    try:
        weather = _fetch_open_meteo(lat, lon, timezone, forecast_days=forecast_days)
    except Exception as exc:
        return {"error": f"Could not fetch weather: {exc}"}

    if forecast_days > 1:
        day_weather = _extract_day_from_weather(weather, target_date)
        if not day_weather:
            return {"error": f"No forecast data available for {target_date}."}
        weather = day_weather

    sc, weather_meta = _weather_to_scenario(weather, country=country)
    spec = BatterySpec()

    idle_result = evaluate(np.zeros(len(sc.load_kw)), sc.solar_kw, sc.wind_kw,
                           sc.load_kw, sc.price_eur_mwh, spec)

    rb_power = rule_based_dispatch(sc.solar_kw, sc.wind_kw, sc.load_kw, spec)
    rb_result = evaluate(rb_power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)

    best, convergence = run_ga(spec, sc, GA_POP, GA_GEN, seed=42)
    power = decode(best, spec)
    result = evaluate(power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)

    facts = extract_day_facts(
        hours=[t.hour for t in sc.timestamps],
        solar_kw=sc.solar_kw, wind_kw=sc.wind_kw, load_kw=sc.load_kw,
        price_eur_mwh=sc.price_eur_mwh, battery_kw=power,
        date=str(sc.timestamps[0].date()),
    )

    try:
        current_hour = int(pd.Timestamp.now(tz=timezone).hour)
    except Exception:
        current_hour = int(pd.Timestamp.now(tz="UTC").hour)

    import math

    def _sf(v, decimals=2):
        f = float(v)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else round(f, decimals)

    idle_cost = _sf(idle_result["total_cost"])
    rb_cost = _sf(rb_result["total_cost"])
    ga_cost = _sf(result["total_cost"])

    return {
        "date": str(sc.timestamps[0].date()),
        "current_hour": current_hour,
        "lat": lat,
        "lon": lon,
        "timezone": timezone,
        "timestamps": [ts.isoformat() for ts in sc.timestamps],
        "weather": weather_meta,
        "solar_kw": [_sf(v) for v in sc.solar_kw],
        "wind_kw": [_sf(v) for v in sc.wind_kw],
        "load_kw": [_sf(v) for v in sc.load_kw],
        "battery_kw": [_sf(v) for v in power],
        "soc": [_sf(v, 4) for v in result["soc"]],
        "import_kw": [_sf(v) for v in result["import_kw"]],
        "export_kw": [_sf(v) for v in result["export_kw"]],
        "total_cost": ga_cost,
        "import_cost": _sf(result["import_cost"]),
        "export_revenue": _sf(result["export_revenue"]),
        "degradation_cost": _sf(result["degradation_cost"]),
        "comparison": {
            "no_battery": idle_cost,
            "rule_based": rb_cost,
            "ga_optimised": ga_cost,
            "saving_vs_idle_pct": _sf((1 - ga_cost / idle_cost) * 100, 1) if idle_cost else 0,
            "saving_vs_rule_pct": _sf((1 - ga_cost / rb_cost) * 100, 1) if rb_cost else 0,
        },
        "explanation": render_template(facts),
        "convergence": [
            {"gen": row["generation"], "best": _sf(row["best"])}
            for row in convergence if row["generation"] % 10 == 0
        ] if convergence else [],
    }


class ChatRequest(BaseModel):
    solar_kw: float | None = Field(None, ge=0, le=10000, description="Solar generation kW — used flat for all 24 hours")
    wind_kw: float | None = Field(None, ge=0, le=10000, description="Wind generation kW — used flat for all 24 hours")
    load_kw: float | None = Field(None, ge=0, le=50000, description="Demand/load kW — used flat for all 24 hours")
    price_per_kwh: float | None = Field(None, ge=0, le=100, description="Electricity price in $/kWh or €/kWh — used as-is, no adders")
    battery_kwh: float | None = Field(None, ge=5, le=10000, description="Battery capacity kWh")
    soc_pct: float | None = Field(None, ge=0, le=100, description="Initial state of charge %")
    question: str = Field("", max_length=1000, description="Optional question about the results")


def _build_flat_scenario(req: ChatRequest) -> Scenario:
    """Build a 24h scenario using the user's values as FLAT constants.
    No bell curves, no TOU shaping — exactly what the user typed."""
    hours = 24
    timestamps = pd.date_range("2025-01-01", periods=hours, freq="h")

    solar = np.full(hours, req.solar_kw if req.solar_kw is not None else 0.0)
    wind = np.full(hours, req.wind_kw if req.wind_kw is not None else 0.0)
    load = np.full(hours, req.load_kw if req.load_kw is not None else 100.0)

    # Convert $/kWh to €/MWh: user's price is the TOTAL price, no hidden adders
    if req.price_per_kwh is not None:
        price_eur_mwh = np.full(hours, req.price_per_kwh * 1000.0)
    else:
        price_eur_mwh = np.full(hours, 180.0)  # ~$0.18/kWh default

    return Scenario(
        timestamps=timestamps,
        solar_kw=solar,
        wind_kw=wind,
        load_kw=load,
        price_eur_mwh=price_eur_mwh,
    )


def _evaluate_flat(power_kw: np.ndarray, scen: Scenario, spec: BatterySpec) -> dict:
    """Evaluate a battery schedule using the user's price directly.
    No IMPORT_ADDER — the user's price IS the import price."""
    from src.env.battery import soc_trajectory, degradation_cost

    net = scen.solar_kw + scen.wind_kw + power_kw - scen.load_kw
    grid_kw = -net
    import_kw = np.clip(grid_kw, 0, None)
    export_kw = np.clip(-grid_kw, 0, None)

    # User's price is the full price — import and export use the same rate
    price_per_kwh = scen.price_eur_mwh / 1000.0
    import_cost = float(np.sum(import_kw * price_per_kwh))
    export_revenue = float(np.sum(export_kw * price_per_kwh * 0.5))  # export at 50% of retail

    soc = soc_trajectory(power_kw, spec)
    deg_cost = degradation_cost(soc, spec)

    # SOC penalties
    soc_under = np.clip(spec.soc_min - soc, 0, None)
    soc_over = np.clip(soc - spec.soc_max, 0, None)
    penalties = 5000.0 * float(np.sum(soc_under) + np.sum(soc_over))

    # Power over-limit penalties
    power_over = np.clip(np.abs(power_kw) - spec.max_power_kw, 0, None)
    penalties += 1000.0 * float(np.sum(power_over))

    total = import_cost - export_revenue + deg_cost + penalties

    return {
        "total_cost": total,
        "import_cost": import_cost,
        "export_revenue": export_revenue,
        "degradation_cost": deg_cost,
        "penalties": penalties,
        "soc": soc,
        "import_kw": import_kw,
        "export_kw": export_kw,
    }


def _optimise_flat(scen: Scenario, spec: BatterySpec) -> dict:
    """Run GA optimisation using the flat evaluator (no hidden adders)."""
    import random
    from deap import base as dbase, creator, tools
    from src.optimization.ga_scheduler import (
        HOURS, CX_ETA, MUT_ETA, GENE_MUT_PROB, CX_PROB, ELITE_N, TOURNAMENT_K,
        init_individual, decode, mate, mutate,
    )

    random.seed(42)
    toolbox = dbase.Toolbox()
    toolbox.register("individual", init_individual, spec)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def fitness(individual):
        power = decode(individual, spec)
        result = _evaluate_flat(power, scen, spec)
        return (result["total_cost"],)

    toolbox.register("evaluate", fitness)
    toolbox.register("mate", mate, spec=spec)
    toolbox.register("mutate", mutate, spec=spec)
    toolbox.register("select", tools.selTournament, tournsize=TOURNAMENT_K)

    pop = toolbox.population(n=GA_POP)
    for ind in pop:
        ind.fitness.values = toolbox.evaluate(ind)

    for gen in range(GA_GEN):
        elites = tools.selBest(pop, ELITE_N)
        offspring = list(map(toolbox.clone, toolbox.select(pop, GA_POP - ELITE_N)))
        for c1, c2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CX_PROB:
                toolbox.mate(c1, c2)
                del c1.fitness.values
                del c2.fitness.values
        for ind in offspring:
            toolbox.mutate(ind)
            del ind.fitness.values
        for ind in offspring:
            ind.fitness.values = toolbox.evaluate(ind)
        pop = elites + offspring

    best = tools.selBest(pop, 1)[0]
    power = decode(best, spec)
    result = _evaluate_flat(power, scen, spec)
    return {
        "cost": round(result["total_cost"], 2),
        "import_cost": round(result["import_cost"], 2),
        "export_revenue": round(result["export_revenue"], 2),
        "degradation_cost": round(result["degradation_cost"], 2),
        "battery_kw": [round(float(v), 2) for v in power],
        "soc": [round(float(v), 4) for v in result["soc"]],
    }


@app.post("/chat")
def chat(req: ChatRequest):
    battery_kwh = req.battery_kwh if req.battery_kwh is not None else 300.0
    spec = _spec_for(battery_kwh)
    if req.soc_pct is not None:
        spec = replace(spec, soc_init=req.soc_pct / 100.0)

    scen = _build_flat_scenario(req)
    result = _optimise_flat(scen, spec)

    # Baseline: no battery
    idle_result = _evaluate_flat(np.zeros(24), scen, spec)
    baseline_cost = round(idle_result["total_cost"], 2)

    delta = result["cost"] - baseline_cost
    denom = abs(baseline_cost) if baseline_cost else 1.0

    # Compute schedule summary
    power = np.array(result["battery_kw"])
    total_charge = round(float(np.sum(np.clip(-power, 0, None))), 1)
    total_discharge = round(float(np.sum(np.clip(power, 0, None))), 1)
    usable = round(spec.capacity_kwh * (spec.soc_max - spec.soc_min), 1)

    # Build charge/discharge windows
    schedule = []
    i = 0
    while i < 24:
        p = power[i]
        if abs(p) < 3:
            i += 1
            continue
        action = "discharge" if p > 0 else "charge"
        j = i
        while j + 1 < 24 and ((power[j+1] > 3 and action == "discharge") or
                               (power[j+1] < -3 and action == "charge")):
            j += 1
        window_power = power[i:j+1]
        schedule.append({
            "action": action,
            "start": f"{i:02d}:00",
            "end": f"{j+1:02d}:00",
            "hours": j - i + 1,
            "avg_power_kw": round(float(np.mean(np.abs(window_power))), 1),
            "energy_kwh": round(float(np.sum(np.abs(window_power))), 1),
        })
        i = j + 1

    # Build explanation
    price_kwh = req.price_per_kwh if req.price_per_kwh is not None else 0.18
    parts = []
    parts.append(f"With your inputs — solar {req.solar_kw or 0} kW, wind {req.wind_kw or 0} kW, "
                 f"demand {req.load_kw or 100} kW, price ${price_kwh}/kWh, "
                 f"battery {battery_kwh} kWh ({spec.soc_init*100:.0f}% charged):")
    parts.append(f"")
    parts.append(f"Optimised daily cost: €{result['cost']:.2f} "
                 f"(import €{result['import_cost']:.2f}, "
                 f"export revenue €{result['export_revenue']:.2f}, "
                 f"degradation €{result['degradation_cost']:.2f}).")

    if abs(delta) >= 0.005:
        direction = "saves" if delta < 0 else "costs"
        parts.append(f"vs. no battery (€{baseline_cost:.2f}): {direction} €{abs(delta):.2f} "
                     f"({delta/denom*100:+.1f}%).")

    parts.append(f"")
    charge_cycles = total_charge / usable if usable > 0 else 0
    discharge_cycles = total_discharge / usable if usable > 0 else 0
    parts.append(f"Battery schedule: charged {total_charge} kWh, discharged {total_discharge} kWh "
                 f"(usable capacity: {usable} kWh, max power: {spec.max_power_kw:.0f} kW).")
    if max(charge_cycles, discharge_cycles) > 1.1:
        parts.append(f"This is ~{max(charge_cycles, discharge_cycles):.1f} full cycles in 24h — "
                     f"the battery charges and discharges multiple times.")

    for w in schedule:
        parts.append(f"  {w['action'].title()} {w['start']}–{w['end']}: "
                     f"~{w['avg_power_kw']} kW avg, {w['energy_kwh']} kWh over {w['hours']}h.")

    # Recommendation
    net = (req.solar_kw or 0) + (req.wind_kw or 0) - (req.load_kw or 100)
    if net > 0:
        parts.append(f"")
        parts.append(f"Your renewables ({(req.solar_kw or 0) + (req.wind_kw or 0)} kW) exceed "
                     f"demand ({req.load_kw or 100} kW) by {net:.0f} kW — the battery stores "
                     f"surplus and discharges when needed.")
    else:
        parts.append(f"")
        parts.append(f"Demand ({req.load_kw or 100} kW) exceeds renewables "
                     f"({(req.solar_kw or 0) + (req.wind_kw or 0)} kW) by {-net:.0f} kW — "
                     f"the battery helps reduce grid imports during peak price periods.")

    return {
        "reply": "\n".join(parts),
        "params_used": {
            "solar_kw": req.solar_kw,
            "wind_kw": req.wind_kw,
            "load_kw": req.load_kw,
            "price_per_kwh": req.price_per_kwh,
            "battery_kwh": req.battery_kwh,
            "soc_pct": req.soc_pct,
        },
        "result": {
            "new_cost": result["cost"],
            "baseline_cost": baseline_cost,
            "delta": round(delta, 2),
            "delta_pct": round(delta / denom * 100, 1),
            "import_cost": result["import_cost"],
            "export_revenue": result["export_revenue"],
            "degradation_cost": result["degradation_cost"],
        },
        "schedule": schedule,
        "totals": {
            "charge_kwh": total_charge,
            "discharge_kwh": total_discharge,
            "usable_capacity_kwh": usable,
            "max_power_kw": round(spec.max_power_kw, 1),
            "cycles": round(max(charge_cycles, discharge_cycles), 1),
        },
        "hourly": {
            "battery_kw": result["battery_kw"],
            "soc_pct": [round(s * 100, 1) for s in result["soc"]],
        },
    }


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    context: dict = Field(default_factory=dict, description="The last /chat response to answer questions about")


@app.post("/ask")
def ask(req: AskRequest):
    """Answer a free-text question about the last optimization result."""
    key = os.environ.get("GROQ_API_KEY")
    ctx = req.context

    if key and key != "your_key_here":
        system = (
            "You are an assistant for a renewable-energy microgrid battery optimiser. "
            "The user ran an optimization and now has a follow-up question. "
            "You have the full optimization results as context.\n\n"
            "Rules:\n"
            "1. Answer based ONLY on the provided data — never invent numbers.\n"
            "2. Never mention historical dates, datasets, or reference days.\n"
            "3. If the user asks about values, use the exact params_used and result data.\n"
            "4. If the user asks 'why' the battery charged/discharged at a time, explain "
            "   using the schedule, renewable surplus/deficit, and price.\n"
            "5. If the user asks about efficiency, use: battery efficiency ~95% round-trip "
            "   (sqrt(0.9487) each way), SOC bounds 20-90%.\n"
            "6. Keep answers conversational, 2-5 sentences. Be specific with numbers.\n"
            "7. If there's no optimization context, help the user understand what inputs "
            "   they can provide (solar kW, wind kW, demand kW, price $/kWh, battery kWh, SOC %)."
        )

        user_content = json.dumps({
            "question": req.question,
            "optimization_context": ctx,
        })

        body = json.dumps({
            "model": GROQ_MODEL,
            "temperature": 0.3,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        }).encode("utf-8")

        http_req = urllib.request.Request(
            GROQ_URL, data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "renewable-optimizer/1.0",
            },
        )
        try:
            with urllib.request.urlopen(http_req, timeout=20) as resp:
                payload = json.loads(resp.read())
            reply = payload["choices"][0]["message"]["content"].strip()
            return {"reply": reply}
        except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
            pass

    # Deterministic fallback when Groq is unavailable
    q = req.question.lower()
    result = ctx.get("result", {})
    params = ctx.get("params_used", {})
    schedule = ctx.get("schedule", [])
    totals = ctx.get("totals", {})

    if not result:
        return {"reply": "No optimization has been run yet. Enter your values above (solar kW, wind kW, demand kW, price $/kWh, battery kWh, charge %) and click Optimize first."}

    if any(w in q for w in ["why", "charge", "discharg", "when"]):
        if schedule:
            lines = []
            for w in schedule:
                lines.append(f"{w['action'].title()} {w['start']}–{w['end']}: "
                             f"{w['avg_power_kw']} kW avg, {w['energy_kwh']} kWh")
            solar = params.get("solar_kw", 0) or 0
            wind = params.get("wind_kw", 0) or 0
            load = params.get("load_kw", 0) or 0
            net = solar + wind - load
            reason = ("renewables exceed demand" if net > 0
                      else "demand exceeds renewables")
            return {"reply": f"The battery schedule has {len(schedule)} windows. "
                    f"Since {reason} by {abs(net):.0f} kW, the optimizer "
                    f"uses the battery to {'store surplus' if net > 0 else 'reduce imports'}. "
                    f"Here's the breakdown:\n" + "\n".join(lines)}
        return {"reply": "The battery was mostly idle — the optimizer found no beneficial charge/discharge windows with your inputs."}

    if any(w in q for w in ["cost", "save", "saving", "expensive", "cheap", "price"]):
        return {"reply": f"The optimized daily cost is €{result.get('new_cost', 0):.2f}. "
                f"Without the battery it would be €{result.get('baseline_cost', 0):.2f}, "
                f"so the battery {'saves' if result.get('delta', 0) < 0 else 'costs'} "
                f"€{abs(result.get('delta', 0)):.2f} per day ({result.get('delta_pct', 0):+.1f}%). "
                f"Import cost: €{result.get('import_cost', 0)}, "
                f"export revenue: €{result.get('export_revenue', 0)}, "
                f"degradation: €{result.get('degradation_cost', 0)}."}

    if any(w in q for w in ["battery", "soc", "cycle", "capacity"]):
        return {"reply": f"Battery: {params.get('battery_kwh', 300)} kWh capacity, "
                f"{totals.get('usable_capacity_kwh', 0)} kWh usable (SOC 20-90%), "
                f"max power {totals.get('max_power_kw', 0)} kW. "
                f"Today it charged {totals.get('charge_kwh', 0)} kWh and "
                f"discharged {totals.get('discharge_kwh', 0)} kWh "
                f"(~{totals.get('cycles', 0)} full cycles). "
                f"Round-trip efficiency is ~95%."}

    if any(w in q for w in ["solar", "wind", "renewable", "generation"]):
        solar = params.get("solar_kw", 0) or 0
        wind = params.get("wind_kw", 0) or 0
        load = params.get("load_kw", 0) or 0
        total_re = solar + wind
        return {"reply": f"Your renewables: solar {solar} kW + wind {wind} kW = {total_re} kW total. "
                f"Demand is {load} kW, so you have a "
                f"{'surplus of ' + str(total_re - load) + ' kW' if total_re > load else 'deficit of ' + str(load - total_re) + ' kW'}. "
                f"Daily generation: solar {solar * 24} kWh, wind {wind * 24} kWh."}

    # Generic fallback
    return {"reply": f"Based on your optimization: daily cost €{result.get('new_cost', 0):.2f}, "
            f"the battery charged {totals.get('charge_kwh', 0)} kWh and "
            f"discharged {totals.get('discharge_kwh', 0)} kWh across "
            f"{len(schedule)} windows. Could you be more specific about what you'd like to know?"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
