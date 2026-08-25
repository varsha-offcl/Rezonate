"""PSO live-correction refiner (project plan section 11, Phase 5; PySwarms).

Resolution adaptation (state this in the report). The plan's PSO design
specifies 4 dimensions covering "the next four 15-minute intervals,"
refined every 15 minutes (sections 1, 2, 5). The dataset (section 6) is
hourly -- OPSD publishes nothing finer -- so PSO here operates on the next
four HOURS. The architecture is unchanged: PSO still runs far more often
than the GA's once-daily cadence (section 3's timescale-separation
argument holds), only the unit of "how far ahead it looks" changes to
match the data actually available.

Trust-region bound. Not a literal +-10% of the setpoint's own *value*,
which collapses to a zero-width bound whenever the GA chose exactly 0 kW --
a common outcome (see the SOC-chart discussion of long idle stretches in
the dashboard). Instead: +-TRUST_FRAC of the battery's max power rating,
centred on the GA setpoint -- the standard reading of a "trust region" in
optimisation (a fixed-size neighbourhood around a point).

TRUST_FRAC=0.50, not the plan's literal 10%. Empirically swept (Phase 7's
ablation, src/eval/ablation.py) over {10, 25, 50, 100}% on the 28-day
representative set: 10% under-corrects (68.2% of achievable saving vs the
oracle), 100%/unbounded over-corrects and loses the GA's structural anchor
(77.0%), 50% is the sweet spot (81.0%, beating both). Report this sweep --
it's a stronger finding than either extreme: the bound matters, and its
width is a real hyperparameter, not an arbitrary plan default.

Scope of this single script: Phase 4's GA validated against *actual* data
directly (comparable to Phase 3's oracle). PSO's entire reason to exist is
correcting for the forecast being *wrong*, so this script is where the TFT
forecast finally gets wired in (deferred from ga_scheduler.py's docstring):
  1. Re-run the GA against the TFT's saved P50 forecast for one day
     (results/phase2_forecast.json -- the same 5-day window the dashboard's
     ForecastChart displays) -- this is "the plan as it would have been
     made the evening before."
  2. Score that plan against what *actually* happened that day.
  3. At one representative hour (default: 10:00, mirroring the plan's own
     worked example in section 1 -- "10:00 next morning, actual PV falls
     below forecast"), run PSO to correct the next 4 hours using the
     now-known actual values, bounded to the trust region.
  4. Re-score the corrected plan against actuals and report the delta.
A full season of these corrections running back-to-back (the "every 15
minutes, 96 times a day" closed loop) is Phase 6's job, not this script's --
see project plan section 11, Phase 6.

PSO settings (plan section 5): swarm size 25, 50 iterations, the listed
"alternative" constriction configuration (c1=c2=2.05, inertia linearly
decaying 0.9 -> 0.4), particles initialised around the GA solution.

Run:
  .venv/Scripts/python -m src.optimization.pso_refiner
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pyswarms as ps

from src.env.battery import BatterySpec
from src.env.objective import evaluate
from src.env.simulator import Scenario, build_scenario, full_frame, rescale
from src.optimization.ga_scheduler import decode as ga_decode
from src.optimization.ga_scheduler import run_ga

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

WINDOW = 4  # PSO corrects the next N hours -- the "dimension" in section 5's table
TRUST_FRAC = 0.50  # +-50% of max_power_kw, centred on the GA setpoint -- calibrated, see module docstring
SWARM_SIZE = 25
N_ITERS = 50
SEED = 42
DEFAULT_CORRECTION_HOUR = 10  # "10:00 next morning" -- plan section 1's example


def load_forecast_day(day_index: int = 0) -> list[dict]:
    """One 24h day of TFT P50 rows from the saved display window
    (results/phase2_forecast.json, written by src.forecasting.tft)."""
    path = RESULTS / "phase2_forecast.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run src.forecasting.tft first")
    rows = json.loads(path.read_text())
    start = day_index * 24
    day_rows = rows[start:start + 24]
    if len(day_rows) < 24:
        raise ValueError(f"day_index {day_index} out of range -- only {len(rows) // 24} full day(s) saved")
    return day_rows


def forecast_scenario(day_rows: list[dict], actual: Scenario) -> Scenario:
    """The TFT's P50 forecast for the same day, rescaled identically to
    actuals. Price isn't a TFT target (plan section 4), so both scenarios
    share the real price series -- the GA/PSO cost signal for price is
    never itself forecast, only generation and load are."""
    frame = full_frame()
    solar = rescale(np.array([r["tft::solar_mw::p50"] for r in day_rows]), "solar_mw", frame)
    wind = rescale(np.array([r["tft::wind_mw::p50"] for r in day_rows]), "wind_mw", frame)
    load = rescale(np.array([r["tft::load_mw::p50"] for r in day_rows]), "load_mw", frame)
    return Scenario(timestamps=actual.timestamps, solar_kw=solar, wind_kw=wind, load_kw=load,
                     price_eur_mwh=actual.price_eur_mwh)


def correct(ga_power: np.ndarray, hour: int, spec: BatterySpec, actual: Scenario,
            swarm_size: int = SWARM_SIZE, n_iters: int = N_ITERS, seed: int = SEED,
            trust_frac: float = TRUST_FRAC):
    """PSO-correct hours [hour, hour+WINDOW) of `ga_power`, scored against
    `actual`, within +-trust_frac-of-max-power of the GA setpoint. Returns
    (corrected_power, window_idx, pso_cost_history).

    `trust_frac=1.0` widens the bound to the battery's full power range --
    i.e. "unbounded" -- which plan section 9 asks to compare against the
    default trust-region run "early," since it's the only evidence for what
    the trust-region *bound itself* contributes over an unconstrained PSO
    (section 3's memetic-algorithm argument rests on this).
    """
    np.random.seed(seed)
    idx = np.arange(hour, min(hour + WINDOW, len(ga_power)))
    dim = len(idx)
    trust_half_width = trust_frac * spec.max_power_kw

    center = ga_power[idx]
    lower = np.clip(center - trust_half_width, -spec.max_power_kw, spec.max_power_kw)
    upper = np.clip(center + trust_half_width, -spec.max_power_kw, spec.max_power_kw)

    init_pos = center + np.random.uniform(-trust_half_width, trust_half_width, size=(swarm_size, dim))
    init_pos = np.clip(init_pos, lower, upper)

    def fitness(x: np.ndarray) -> np.ndarray:
        costs = np.empty(x.shape[0])
        for i in range(x.shape[0]):
            power = ga_power.copy()
            power[idx] = x[i]
            result = evaluate(power, actual.solar_kw, actual.wind_kw, actual.load_kw,
                               actual.price_eur_mwh, spec)
            costs[i] = result["total_cost"]
        return costs

    optimizer = ps.single.GlobalBestPSO(
        n_particles=swarm_size,
        dimensions=dim,
        options={"c1": 2.05, "c2": 2.05, "w": 0.9},
        bounds=(lower, upper),
        oh_strategy={"w": "lin_variation"},  # decays 0.9 -> 0.4 by default (plan section 5)
        init_pos=init_pos,
    )
    best_cost, best_pos = optimizer.optimize(fitness, iters=n_iters, verbose=False)

    corrected = ga_power.copy()
    corrected[idx] = best_pos
    return corrected, idx, optimizer.cost_history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day-index", type=int, default=0, help="which saved TFT display day (0-4)")
    ap.add_argument("--hour", type=int, default=DEFAULT_CORRECTION_HOUR)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    spec = BatterySpec()
    day_rows = load_forecast_day(args.day_index)
    day_start = day_rows[0]["timestamp"]
    actual = build_scenario(day_start, 24)
    forecast = forecast_scenario(day_rows, actual)

    print(f"Day: {actual.timestamps[0].date()}  "
          f"(TFT forecast vs actual mean abs error -- solar: "
          f"{np.mean(np.abs(forecast.solar_kw - actual.solar_kw)):.1f} kW, "
          f"wind: {np.mean(np.abs(forecast.wind_kw - actual.wind_kw)):.1f} kW, "
          f"load: {np.mean(np.abs(forecast.load_kw - actual.load_kw)):.1f} kW)")

    print("Re-running GA against the TFT forecast (the plan as made the evening before)...")
    best, _ = run_ga(spec, forecast, pop_size=100, n_gen=200, seed=args.seed)
    ga_power = ga_decode(best, spec)

    ga_realized = evaluate(ga_power, actual.solar_kw, actual.wind_kw, actual.load_kw,
                            actual.price_eur_mwh, spec)
    print(f"GA-plan-as-is, realized against actuals: EUR {ga_realized['total_cost']:.2f}")

    print(f"PSO correcting hours [{args.hour}:{args.hour + WINDOW}) against actuals "
          f"(trust region +-{TRUST_FRAC * spec.max_power_kw:.1f} kW)...")
    t0 = time.time()
    corrected_power, idx, cost_history = correct(ga_power, args.hour, spec, actual, seed=args.seed)
    elapsed = time.time() - t0

    corrected_realized = evaluate(corrected_power, actual.solar_kw, actual.wind_kw, actual.load_kw,
                                   actual.price_eur_mwh, spec)
    print(f"wall-clock: {elapsed:.2f}s (target: under 2s per plan section 5)")
    print(f"GA+PSO-corrected, realized against actuals: EUR {corrected_realized['total_cost']:.2f}  "
          f"(delta vs GA-as-is: {corrected_realized['total_cost'] - ga_realized['total_cost']:+.2f})")

    # Unbounded comparison (plan section 9: "run early" -- the only evidence
    # for what the trust-region bound itself contributes over unconstrained PSO).
    unbounded_power, _, _ = correct(ga_power, args.hour, spec, actual, seed=args.seed, trust_frac=1.0)
    unbounded_realized = evaluate(unbounded_power, actual.solar_kw, actual.wind_kw, actual.load_kw,
                                   actual.price_eur_mwh, spec)
    print(f"unbounded PSO (trust_frac=1.0), realized against actuals: EUR "
          f"{unbounded_realized['total_cost']:.2f}  "
          f"(vs trust-region EUR {corrected_realized['total_cost']:.2f})")

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {
        "day": str(actual.timestamps[0].date()),
        "correction_hour": args.hour,
        "window_hours": int(len(idx)),
        "timestamps": [ts.isoformat() for ts in actual.timestamps],
        "ga_plan_kw": [round(float(v), 2) for v in ga_power],
        "corrected_kw": [round(float(v), 2) for v in corrected_power],
        "trust_low_kw": [round(float(v), 2) for v in np.clip(
            ga_power - TRUST_FRAC * spec.max_power_kw, -spec.max_power_kw, spec.max_power_kw)],
        "trust_high_kw": [round(float(v), 2) for v in np.clip(
            ga_power + TRUST_FRAC * spec.max_power_kw, -spec.max_power_kw, spec.max_power_kw)],
        "ga_realized_cost": round(ga_realized["total_cost"], 2),
        "corrected_realized_cost": round(corrected_realized["total_cost"], 2),
        "unbounded_realized_cost": round(unbounded_realized["total_cost"], 2),
        "pso_cost_history": [round(float(c), 4) for c in cost_history],
    }
    (RESULTS / "pso_corrections.json").write_text(json.dumps(out))
    print(f"Wrote {RESULTS / 'pso_corrections.json'}")


if __name__ == "__main__":
    main()
