"""Export contract between Python and React (project plan section 7/11).

Phase 1 wrote forecast.json, metrics.json, overview.json (baselines only).
Phase 2 extends the contract: forecast.json gains the TFT (with P10/P50/P90
quantile bands) and LSTM per-model series, metrics.json gains their rows, and
importance.json is added from the TFT's variable-selection weights.

The Phase-2 model outputs are read from results/phase2_*.json (written by
src.forecasting.tft). If those files are absent this falls back cleanly to the
Phase-1 baseline-only export, so the dashboard always builds.

Phase 3 adds dispatch.json, soc.json, oracle.json: the rule-based floor and
the MILP oracle ceiling (src/optimization/), simulated over the full test
season (src/env/). Unlike Phase 2 these are computed live every export run
(a full-season LP solve takes ~1-2s, so there is no results/ cache to fall
back to).

Phase 4 adds ga_convergence.json and schedule.json, read from
results/ga_convergence.json / results/ga_schedule.json (written by
src.optimization.ga_scheduler -- a GA run isn't cheap enough to redo on
every export, so like Phase 2 it's cached and falls back cleanly when absent.

Phase 5 adds pso_corrections.json, read from results/pso_corrections.json
(written by src.optimization.pso_refiner) -- same cache-and-fall-back pattern.

Phase 8b adds explanation.json (the "why this decision" facts + template text)
and per-hour price to dispatch.json, both via src.explain.decision_facts. The
standalone src.explain.generate produces the same explanation.json from just the
display window when a full season regen isn't wanted.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.splits import load_splits
from src.env.battery import BatterySpec
from src.env.objective import evaluate as eval_objective
from src.env.simulator import test_window
from src.explain.decision_facts import facts_for_best_day, render_template
from src.forecasting.baselines import TARGETS, run_for_target
from src.optimization import milp_oracle
from src.optimization.rule_based import dispatch as rule_based_dispatch

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "data"
RESULTS = ROOT / "results"

DISPATCH_DISPLAY_HOURS = 24 * 7  # one representative week for the dispatch/SOC charts

BASELINE_MODELS = ["persistence", "seasonal_naive", "lightgbm"]
# Order the dashboard's model switcher offers, best-first-ish.
ALL_MODELS = ["tft", "lstm", "lightgbm", "seasonal_naive", "persistence"]
FORECAST_WINDOW_HOURS = 24 * 5  # matches tft.py DISPLAY_DAYS


def r(x, ndigits=3):
    if isinstance(x, (float, np.floating)):
        if np.isnan(x):
            return None
        return round(float(x), ndigits)
    return x


def load_phase2():
    """Return (metrics, forecast_by_ts, importance) or (None, None, None)."""
    fmet = RESULTS / "phase2_metrics.json"
    ffor = RESULTS / "phase2_forecast.json"
    fimp = RESULTS / "phase2_importance.json"
    if not (fmet.exists() and ffor.exists()):
        return None, None, None
    metrics = json.loads(fmet.read_text())
    rows = json.loads(ffor.read_text())
    forecast_by_ts = {row["timestamp"]: row for row in rows}
    importance = json.loads(fimp.read_text()) if fimp.exists() else None
    return metrics, forecast_by_ts, importance


def load_phase4():
    """Return (convergence_rows, schedule_rows) or (None, None)."""
    fconv = RESULTS / "ga_convergence.json"
    fsched = RESULTS / "ga_schedule.json"
    if not (fconv.exists() and fsched.exists()):
        return None, None
    return json.loads(fconv.read_text()), json.loads(fsched.read_text())


def build_convergence_json(convergence: list) -> dict:
    return {"rows": [{"generation": row["generation"], "best": r(row["best"], 2),
                       "mean": r(row["mean"], 2)} for row in convergence]}


def build_schedule_json(schedule: list) -> dict:
    return {
        "timestamps": [row["timestamp"] for row in schedule],
        "battery_kw": [r(row["battery_kw"], 2) for row in schedule],
    }


def load_phase5():
    """Return the pso_corrections dict, or None."""
    fpso = RESULTS / "pso_corrections.json"
    return json.loads(fpso.read_text()) if fpso.exists() else None


def load_learning():
    """Return the closed-loop learning dict (warm-start + self-adaptive), or None."""
    flearn = RESULTS / "learning.json"
    return json.loads(flearn.read_text()) if flearn.exists() else None


def load_drift():
    """Return the drift-detection dict (forecast error over the season), or None."""
    fdrift = RESULTS / "drift.json"
    return json.loads(fdrift.read_text()) if fdrift.exists() else None


def load_ablation():
    """Return the ablation-grid dict (the headline results table), or None."""
    fab = RESULTS / "ablation.json"
    return json.loads(fab.read_text()) if fab.exists() else None


def build_pso_json(pso: dict) -> dict:
    return {
        "day": pso["day"],
        "correction_hour": pso["correction_hour"],
        "window_hours": pso["window_hours"],
        "timestamps": pso["timestamps"],
        "ga_plan_kw": [r(v, 2) for v in pso["ga_plan_kw"]],
        "corrected_kw": [r(v, 2) for v in pso["corrected_kw"]],
        "trust_low_kw": [r(v, 2) for v in pso["trust_low_kw"]],
        "trust_high_kw": [r(v, 2) for v in pso["trust_high_kw"]],
        "ga_realized_cost": pso["ga_realized_cost"],
        "corrected_realized_cost": pso["corrected_realized_cost"],
        "unbounded_realized_cost": pso.get("unbounded_realized_cost"),
    }


def build_metrics_json(all_results: dict, phase2_metrics: dict | None) -> dict:
    rows = []
    for target, models in all_results.items():
        for model_name, m in models.items():
            rows.append({"target": target, "model": model_name,
                         "rmse": r(m["rmse"], 2), "mae": r(m["mae"], 2),
                         "nrmse": r(m["nrmse"], 4)})
    models_present = list(BASELINE_MODELS)
    if phase2_metrics:
        for model_name, per_target in phase2_metrics.items():  # "tft", "lstm"
            models_present.append(model_name)
            for target, m in per_target.items():
                rows.append({"target": target, "model": model_name,
                             "rmse": r(m["rmse"], 2), "mae": r(m["mae"], 2),
                             "nrmse": r(m["nrmse"], 4)})
    ordered = [m for m in ALL_MODELS if m in models_present]
    return {"rows": rows, "targets": TARGETS, "models": ordered}


def build_forecast_json(all_predictions: dict, forecast_by_ts: dict | None) -> dict:
    """Per-target series over the display window, aligned by timestamp across
    every model. Baselines + actual come from the Phase-1 predictions; the TFT
    bands and LSTM point forecast come from the Phase-2 rows when present.
    """
    out = {}
    for target, (test_idx, predictions) in all_predictions.items():
        n = len(test_idx)
        start = max(0, n - FORECAST_WINDOW_HOURS)
        window_idx = test_idx[start:]

        series = []
        for i, ts in enumerate(window_idx):
            iso = ts.isoformat()
            pos = start + i
            row = {"timestamp": iso, "actual": r(predictions["actual"][pos], 2)}
            for key in BASELINE_MODELS:
                row[key] = r(predictions[key][pos], 2)
            if forecast_by_ts and iso in forecast_by_ts:
                p2 = forecast_by_ts[iso]
                for stat in ("p10", "p50", "p90"):
                    k = f"tft::{target}::{stat}"
                    if k in p2:
                        row[f"tft_{stat}"] = r(p2[k], 2)
                lk = f"lstm::{target}::p50"
                if lk in p2:
                    row["lstm"] = r(p2[lk], 2)
            series.append(row)
        out[target] = series
    return out


def run_phase3() -> dict:
    """Simulate the rule-based floor and the MILP oracle ceiling over the
    full test season (env/objective/optimization; project plan Phase 3).
    Returns the full-season scenario plus both policies' schedules/costs.
    """
    spec = BatterySpec()
    _, _, test = load_splits()
    sc = test_window(len(test))

    # idle = do-nothing baseline (battery never moves): the reference the
    # "% of achievable saving captured" headline is measured from.
    idle_result = eval_objective(np.zeros(len(sc.load_kw)), sc.solar_kw, sc.wind_kw,
                                 sc.load_kw, sc.price_eur_mwh, spec)

    rb_power = rule_based_dispatch(sc.solar_kw, sc.wind_kw, sc.load_kw, spec)
    rb_result = eval_objective(rb_power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)

    oracle_solution = milp_oracle.solve(sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    oracle_power = oracle_solution["battery_power_kw"]
    oracle_result = eval_objective(oracle_power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)

    return {
        "spec": spec,
        "scenario": sc,
        "idle": {"result": idle_result},
        "rule_based": {"power_kw": rb_power, "result": rb_result},
        "oracle": {
            "power_kw": oracle_power,
            "result": oracle_result,
            "linearized_cost": oracle_solution["linearized_cost"],
        },
    }


def build_dispatch_json(phase3: dict) -> dict:
    sc = phase3["scenario"]
    n = min(DISPATCH_DISPLAY_HOURS, len(sc.timestamps))
    out = {
        "timestamps": [ts.isoformat() for ts in sc.timestamps[:n]],
        "solar_kw": [r(v, 2) for v in sc.solar_kw[:n]],
        "wind_kw": [r(v, 2) for v in sc.wind_kw[:n]],
        "load_kw": [r(v, 2) for v in sc.load_kw[:n]],
        "price_eur_mwh": [r(v, 2) for v in sc.price_eur_mwh[:n]],
        "policies": {},
    }
    for name in ("rule_based", "oracle"):
        res = phase3[name]["result"]
        out["policies"][name] = {
            "battery_kw": [r(v, 2) for v in phase3[name]["power_kw"][:n]],
            "import_kw": [r(v, 2) for v in res["import_kw"][:n]],
            "export_kw": [r(v, 2) for v in res["export_kw"][:n]],
        }
    return out


def build_explanation_json(phase3: dict) -> dict:
    """The "why this decision" facts + template text (Phase 8b) for the most
    active full day within the dispatch chart's display window, so the explained
    day is one the user can see on screen. Explains the oracle's schedule --
    the smart, forward-looking policy whose moves have clear reasons.
    """
    sc = phase3["scenario"]
    facts = facts_for_best_day(
        sc.timestamps, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh,
        phase3["oracle"]["power_kw"], within=DISPATCH_DISPLAY_HOURS,
    )
    return {
        "policy": "oracle",
        "date": facts["date"],
        "facts": facts,
        "template_text": render_template(facts),
    }


def build_soc_json(phase3: dict) -> dict:
    sc = phase3["scenario"]
    spec = phase3["spec"]
    n = min(DISPATCH_DISPLAY_HOURS, len(sc.timestamps))
    timestamps = [(sc.timestamps[0] + pd.Timedelta(hours=h)).isoformat() for h in range(n + 1)]
    out = {"timestamps": timestamps, "soc_min": spec.soc_min, "soc_max": spec.soc_max, "policies": {}}
    for name in ("rule_based", "oracle"):
        soc = phase3[name]["result"]["soc"][: n + 1]
        out["policies"][name] = [r(v, 4) for v in soc]
    return out


def build_season_json(phase3: dict) -> dict:
    """Full test season (not the one-week window build_dispatch_json/
    build_soc_json show), for the Live-ops season scrubber (Phase 7.5) --
    it needs a real day to step to, not a lookup into the same week.
    """
    sc = phase3["scenario"]
    n = len(sc.timestamps)
    days = n // 24
    n = days * 24  # drop a partial trailing day so every day has 24h
    out = {
        "days": days,
        "timestamps": [ts.isoformat() for ts in sc.timestamps[:n]],
        "solar_kw": [r(v, 2) for v in sc.solar_kw[:n]],
        "wind_kw": [r(v, 2) for v in sc.wind_kw[:n]],
        "load_kw": [r(v, 2) for v in sc.load_kw[:n]],
        "soc_min": phase3["spec"].soc_min,
        "soc_max": phase3["spec"].soc_max,
        "policies": {},
    }
    for name in ("rule_based", "oracle"):
        res = phase3[name]["result"]
        out["policies"][name] = {
            "battery_kw": [r(v, 2) for v in phase3[name]["power_kw"][:n]],
            "import_kw": [r(v, 2) for v in res["import_kw"][:n]],
            "export_kw": [r(v, 2) for v in res["export_kw"][:n]],
            "soc": [r(v, 4) for v in res["soc"][: n + 1]],
        }
    return out


def build_oracle_json(phase3: dict) -> dict:
    rb = phase3["rule_based"]["result"]
    orc = phase3["oracle"]["result"]
    linearized = phase3["oracle"]["linearized_cost"]

    def breakdown(res, cost_key="total_cost"):
        return {
            cost_key: r(res["total_cost"], 2),
            "import_cost": r(res["import_cost"], 2),
            "export_revenue": r(res["export_revenue"], 2),
            "degradation_cost": r(res["degradation_cost"], 2),
            "penalties": r(res["penalties"], 2),
        }

    idle = phase3["idle"]["result"]
    # "% of the achievable saving captured" (plan section 12's headline framing):
    # how much of the idle->oracle gap a policy closes. 100% = matches the
    # perfect-foresight ceiling; 0% = no better than a battery that never moves.
    headroom = idle["total_cost"] - orc["total_cost"]
    rb_capture = (idle["total_cost"] - rb["total_cost"]) / headroom * 100 if headroom else None

    return {
        "season_hours": len(phase3["scenario"].timestamps),
        "idle": breakdown(idle),
        "rule_based": breakdown(rb),
        "oracle": {
            # "true_cost" (exact rainflow degradation) vs "linearized_cost" (the
            # LP's own piecewise-linear estimate) -- see milp_oracle.py's
            # module docstring for why these two numbers differ.
            **breakdown(orc, cost_key="true_cost"),
            "linearized_cost": r(linearized, 2),
            "linearization_gap": r(orc["total_cost"] - linearized, 2),
        },
        "rule_based_capture_pct": r(rb_capture, 1),
    }


def build_overview_json() -> dict:
    train, val, test = load_splits()
    full = pd.concat([train, val, test])
    return {
        "timestamps": [ts.isoformat() for ts in full.index],
        "solar_mw": [r(v, 1) for v in full["solar_mw"]],
        "wind_mw": [r(v, 1) for v in full["wind_mw"]],
        "load_mw": [r(v, 1) for v in full["load_mw"]],
        "price_eur_mwh": [r(v, 2) for v in full["price_eur_mwh"]],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train, val, test = load_splits()

    all_results, all_predictions = {}, {}
    for target in TARGETS:
        print(f"Running baselines for export: {target}")
        results, predictions, test_idx, _ = run_for_target(target, train, val, test)
        all_results[target] = results
        all_predictions[target] = (test_idx, predictions)

    phase2_metrics, forecast_by_ts, importance = load_phase2()
    if phase2_metrics:
        print(f"Merging Phase-2 models: {list(phase2_metrics.keys())}")
    else:
        print("Phase-2 artifacts not found — exporting baselines only.")

    print("Simulating Phase-3 rule-based floor + MILP oracle over the test season...")
    phase3 = run_phase3()
    print(f"  rule-based: EUR {phase3['rule_based']['result']['total_cost']:.2f}  "
          f"oracle: EUR {phase3['oracle']['result']['total_cost']:.2f}")

    convergence, schedule = load_phase4()
    if convergence:
        print(f"Merging Phase-4 GA results: {len(convergence)} generations, "
              f"{len(schedule)}h schedule")
    else:
        print("Phase-4 GA artifacts not found — run src.optimization.ga_scheduler first.")

    pso = load_phase5()
    if pso:
        print(f"Merging Phase-5 PSO correction: {pso['day']}, hour {pso['correction_hour']}, "
              f"EUR {pso['ga_realized_cost']:.2f} -> {pso['corrected_realized_cost']:.2f}")
    else:
        print("Phase-5 PSO artifacts not found — run src.optimization.pso_refiner first.")

    learning = load_learning()
    if learning:
        s = learning["summary"]
        print(f"Merging Phase-6 closed-loop: warm-start {s['mean_gen_cold']} -> "
              f"{s['mean_gen_warm']} gens ({s['reduction_pct']:+.0f}%)")
    else:
        print("Phase-6 learning artifacts not found — run src.optimization.closed_loop.")

    drift = load_drift()
    if drift:
        print(f"Merging Phase-6 drift detection: {len(drift['trigger_timestamps'])} triggers "
              f"over {len(drift['days'])} days (error mean {drift['error_mean']})")
    else:
        print("Phase-6 drift artifacts not found — run src.forecasting.drift.")

    ablation = load_ablation()
    if ablation:
        print(f"Merging Phase-7 ablation: {len(ablation['rows'])} configs over {ablation['days']} days")
    else:
        print("Phase-7 ablation artifacts not found — run src.eval.ablation.")

    payloads = {
        "metrics.json": build_metrics_json(all_results, phase2_metrics),
        "forecast.json": build_forecast_json(all_predictions, forecast_by_ts),
        "overview.json": build_overview_json(),
        "dispatch.json": build_dispatch_json(phase3),
        "soc.json": build_soc_json(phase3),
        "oracle.json": build_oracle_json(phase3),
        "season.json": build_season_json(phase3),
        "explanation.json": build_explanation_json(phase3),
    }
    if importance is not None:
        payloads["importance.json"] = importance
    if convergence is not None:
        payloads["ga_convergence.json"] = build_convergence_json(convergence)
        payloads["schedule.json"] = build_schedule_json(schedule)
    if pso is not None:
        payloads["pso_corrections.json"] = build_pso_json(pso)
    if learning is not None:
        payloads["learning.json"] = learning  # already export-shaped (rounded in closed_loop)
    if drift is not None:
        payloads["drift.json"] = drift  # already export-shaped (rounded in drift.py)
    if ablation is not None:
        payloads["ablation.json"] = ablation  # already export-shaped (rounded in ablation.py)

    for name, payload in payloads.items():
        path = OUT_DIR / name
        with open(path, "w") as f:
            json.dump(payload, f)
        print(f"Wrote {path} ({path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
