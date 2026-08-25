"""Deterministic decision-fact extraction for the "why this decision"
explanation layer (project plan Phase 8b).

The explanation must be *truthful*. Every claim it makes about why the battery
charged or discharged in a given window -- the times, the renewable surplus,
the price level -- is computed HERE, from the actual scenario (solar/wind/
load/price) and the actual dispatch schedule. The optional language-model
layer (src/api.py's /explain endpoint) is given only these computed facts and
told to introduce no new numbers or reasons; it merely rephrases them into
natural prose. Because the static export (src/export/to_json.py) and the live
endpoint both call this one module, the deterministic template and the
AI-phrased version always describe the same verified facts.

Sign convention (matches env/objective.py and the schedule chart): positive
battery power = discharging (adds supply); negative = charging (adds demand).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Battery moves smaller than this (kW) are optimiser noise, not a deliberate
# charge/discharge decision worth explaining -- they don't start a window.
ACTIVITY_THRESHOLD_KW = 3.0

# How many windows the template narrates. Beyond a handful the paragraph stops
# reading like an explanation and starts reading like a log.
MAX_NARRATED_WINDOWS = 4


def _fmt_hour(h: int) -> str:
    # Windows run *through* the end of their last hour, so an end of 24 means
    # "to midnight" -- keep it as 24:00 rather than wrapping to a confusing 00:00.
    return f"{int(h):02d}:00"


def _price_context(mean_price: float, low_thr: float, high_thr: float) -> str:
    if mean_price <= low_thr:
        return "low"
    if mean_price >= high_thr:
        return "high"
    return "moderate"


def extract_day_facts(hours, solar_kw, wind_kw, load_kw, price_eur_mwh, battery_kw,
                      date: str | None = None) -> dict:
    """Verified facts for a single day. All sequences are equal-length (one
    interval each, typically 24 hourly intervals). `hours` is the hour-of-day
    (0-23) for each interval. Returns a JSON-safe dict.
    """
    hours = [int(h) for h in hours]
    solar = np.asarray(solar_kw, dtype=float)
    wind = np.asarray(wind_kw, dtype=float)
    load = np.asarray(load_kw, dtype=float)
    price = np.asarray(price_eur_mwh, dtype=float)
    batt = np.asarray(battery_kw, dtype=float)
    n = len(batt)

    surplus = solar + wind - load  # >0 renewables exceed load, <0 a deficit

    # "Low"/"high" price is relative to *this day's* own spread -- the battery
    # arbitrages within the day, so the day's quartiles are the honest reference.
    low_thr = float(np.percentile(price, 25))
    high_thr = float(np.percentile(price, 75))

    def action_of(p: float) -> str:
        if p < -ACTIVITY_THRESHOLD_KW:
            return "charge"
        if p > ACTIVITY_THRESHOLD_KW:
            return "discharge"
        return "idle"

    acts = [action_of(p) for p in batt]

    # Group contiguous same-action runs into windows.
    windows = []
    i = 0
    while i < n:
        a = acts[i]
        if a == "idle":
            i += 1
            continue
        j = i
        while j + 1 < n and acts[j + 1] == a:
            j += 1
        idx = list(range(i, j + 1))
        mean_price = float(np.mean(price[idx]))
        mean_surplus = float(np.mean(surplus[idx]))
        windows.append({
            "action": a,
            "start": _fmt_hour(hours[i]),
            "end": _fmt_hour(hours[j] + 1),
            "hours": len(idx),
            "mean_surplus_kw": round(mean_surplus, 1),   # +ve surplus, -ve deficit
            "mean_price_eur_mwh": round(mean_price, 1),
            "price_context": _price_context(mean_price, low_thr, high_thr),
            "energy_kwh": round(float(np.sum(np.abs(batt[idx]))), 1),  # dt = 1h
        })
        i = j + 1

    charge_kwh = round(float(np.sum(np.clip(-batt, 0, None))), 1)
    discharge_kwh = round(float(np.sum(np.clip(batt, 0, None))), 1)
    peak_solar_i = int(np.argmax(solar))
    price_min_i = int(np.argmin(price))
    price_max_i = int(np.argmax(price))

    # Narrate the highest-energy windows first (the decisions that matter most),
    # but present them back in chronological order so the story reads as a day.
    ranked = sorted(windows, key=lambda w: w["energy_kwh"], reverse=True)[:MAX_NARRATED_WINDOWS]
    narrated = sorted(ranked, key=lambda w: w["start"])

    return {
        "date": date,
        "n_active_windows": len(windows),
        "total_charge_kwh": charge_kwh,
        "total_discharge_kwh": discharge_kwh,
        "peak_solar": {"hour": _fmt_hour(hours[peak_solar_i]), "kw": round(float(solar[peak_solar_i]), 1)},
        "price_low": {"hour": _fmt_hour(hours[price_min_i]), "eur_mwh": round(float(price[price_min_i]), 1)},
        "price_high": {"hour": _fmt_hour(hours[price_max_i]), "eur_mwh": round(float(price[price_max_i]), 1)},
        "windows": narrated,
    }


def _cost_phrase(v: float) -> str:
    # Negative cost means the microgrid nets money that day.
    return f"earns €{abs(v):.2f}" if v < 0 else f"costs €{v:.2f}"


def _scenario_change_sentence(chg: dict) -> str:
    """Opening sentence for a what-if re-optimisation: what input changed and
    how the re-optimised day's cost compares to the baseline."""
    solar_pct = chg.get("solar_pct", 0)
    if solar_pct:
        solar_txt = f"solar output {'up' if solar_pct > 0 else 'down'} {abs(solar_pct):.0f}%"
    else:
        solar_txt = "solar output unchanged"

    delta = chg.get("delta", 0.0)
    if abs(delta) < 0.005:
        cmp_txt = "the same cost as the baseline"
    else:
        amount = f"€{abs(delta):.2f} {'less' if delta < 0 else 'more'}"
        cmp_txt = f"{amount} than the baseline ({chg.get('delta_pct', 0):+.1f}%)"

    return (f"With {solar_txt} and a {chg.get('battery_kwh', 0):.0f} kWh battery, the "
            f"re-optimised day {_cost_phrase(chg['new_cost'])} — {cmp_txt}.")


def render_template(facts: dict) -> str:
    """Deterministic plain-language paragraph from extracted facts. This is the
    always-available fallback and the ground truth the LLM only rephrases.
    Uses future tense when the date is ahead of today.
    """
    date = facts.get("date") or "this day"
    parts = []

    # Detect future dates
    is_future = False
    if facts.get("date"):
        try:
            fact_date = pd.Timestamp(facts["date"]).date()
            today = pd.Timestamp.now().date()
            is_future = fact_date > today
        except Exception:
            pass

    # For a what-if result, lead with what changed and its cost effect.
    if facts.get("scenario_change"):
        parts.append(_scenario_change_sentence(facts["scenario_change"]))

    if is_future:
        parts.append(
            f"On {date}, the battery is predicted to make {facts['n_active_windows']} main moves — "
            f"charging about {facts['total_charge_kwh']:.0f} kWh and discharging about "
            f"{facts['total_discharge_kwh']:.0f} kWh across the day."
        )
    else:
        parts.append(
            f"On {date}, the battery made {facts['n_active_windows']} main moves — "
            f"charging about {facts['total_charge_kwh']:.0f} kWh and discharging about "
            f"{facts['total_discharge_kwh']:.0f} kWh across the day."
        )

    for w in facts["windows"]:
        price_phrase = (f"the forecasted price {'will be' if is_future else 'is'} "
                        f"{w['price_context']} (around €{w['mean_price_eur_mwh']:.0f}/MWh)")
        if w["action"] == "charge":
            if w["mean_surplus_kw"] > 0:
                reason = (f"solar and wind {'are expected to' if is_future else ''} exceed demand "
                          f"by about {w['mean_surplus_kw']:.0f} kW and {price_phrase}")
            else:
                reason = price_phrase
            if is_future:
                parts.append(
                    f"Charging {w['start']}–{w['end']}: {reason}, so the battery "
                    f"will store about {w['energy_kwh']:.0f} kWh instead of exporting cheaply."
                )
            else:
                parts.append(
                    f"Charging {w['start']}–{w['end']}: {reason}, so the battery stores "
                    f"about {w['energy_kwh']:.0f} kWh instead of exporting it cheaply."
                )
        else:  # discharge
            deficit = -w["mean_surplus_kw"]
            if deficit > 0:
                reason = (f"demand {'is expected to outstrip' if is_future else 'outstrips'} "
                          f"renewables by about {deficit:.0f} kW and {price_phrase}")
            else:
                reason = price_phrase
            if is_future:
                parts.append(
                    f"Discharging {w['start']}–{w['end']}: {reason}, so the battery "
                    f"will cover about {w['energy_kwh']:.0f} kWh of the gap rather than importing."
                )
            else:
                parts.append(
                    f"Discharging {w['start']}–{w['end']}: {reason}, so the battery covers "
                    f"about {w['energy_kwh']:.0f} kWh of the gap rather than importing at that price."
                )

    return " ".join(parts)


def facts_for_best_day(timestamps, solar_kw, wind_kw, load_kw, price_eur_mwh,
                       battery_kw, within: int | None = None) -> dict:
    """Pick the full calendar day with the most battery activity and return its
    facts. `timestamps` is any sequence pandas can parse. `within` optionally
    restricts the search to the first `within` intervals -- pass the dispatch
    chart's display window so the explained day is one the user can actually see
    on screen.
    """
    ts = pd.to_datetime(list(timestamps))
    df = pd.DataFrame({
        "solar": np.asarray(solar_kw, dtype=float),
        "wind": np.asarray(wind_kw, dtype=float),
        "load": np.asarray(load_kw, dtype=float),
        "price": np.asarray(price_eur_mwh, dtype=float),
        "batt": np.asarray(battery_kw, dtype=float),
    }, index=ts)

    if within is not None:
        df = df.iloc[:within]

    best_date, best_activity, best_group = None, -1.0, None
    for date, group in df.groupby(df.index.normalize()):
        if len(group) != 24:  # only explain complete days
            continue
        activity = float(np.sum(np.abs(group["batt"].to_numpy())))
        if activity > best_activity:
            best_date, best_activity, best_group = date, activity, group

    if best_group is None:
        raise ValueError("No complete 24-hour day found to explain in the given window.")

    g = best_group
    return extract_day_facts(
        hours=[t.hour for t in g.index],
        solar_kw=g["solar"].to_numpy(),
        wind_kw=g["wind"].to_numpy(),
        load_kw=g["load"].to_numpy(),
        price_eur_mwh=g["price"].to_numpy(),
        battery_kw=g["batt"].to_numpy(),
        date=best_date.strftime("%Y-%m-%d"),
    )
