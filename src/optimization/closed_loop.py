"""Closed-loop self-learning for the optimisers (project plan section 11,
Phase 6 -- the "warm-starting" and "self-adaptive parameters" mechanisms).

The plan is careful about wording, and so is this: the *forecaster* learns
from experience (drift-triggered retraining -- see src/forecasting/drift.py);
the *optimisers* do not learn, they converge faster by reusing solutions and
self-tuning their own operators. This module demonstrates the two optimiser
mechanisms and quantifies them:

  * Warm-starting -- seed the next day's GA population with today's elite
    chromosomes instead of starting random. Because consecutive days share a
    daily generation/load shape, yesterday's good schedules are a strong
    starting point, so the GA reaches the same quality in fewer generations.
    Reported as the reduction in generations-to-converge (plan section 11).

  * Self-adaptive mutation -- the per-gene mutation rate rises as the
    population's diversity collapses and eases off while it's still exploring
    (ga_scheduler.adaptive_indpb). Reported as the diversity and mutation-rate
    traces over a run (plan: "Plot both").

PSO's inertia weight is likewise adaptive -- it already decays 0.9->0.4 over
each swarm's run (pso_refiner.py, PySwarms `lin_variation`), the plan's
"inertia weight by swarm convergence" -- so it needs no separate driver here.

Run:
  .venv/Scripts/python -m src.optimization.closed_loop --days 5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.env.battery import BatterySpec
from src.env.simulator import test_window
from src.optimization.ga_scheduler import (
    POP_SIZE,
    N_GEN,
    generations_to_reach,
    run_ga,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

ELITE_CARRY = 20  # how many of yesterday's best chromosomes seed today's population


def run(days: int, pop_size: int, n_gen: int, seed: int = 42) -> dict:
    spec = BatterySpec()
    scenarios = [test_window(24, offset_hours=24 * d) for d in range(days)]

    per_day = []
    carried_elites = None          # elites from the previous WARM run (the live loop)
    rep_curves = None              # cold-vs-warm best-per-gen for the first warm day
    rep_adaptive = None            # diversity/mut trace for the first day's run

    for d, sc in enumerate(scenarios):
        if d == 0:
            # Cold start: nothing to reuse yet. Keep its elites + adaptive trace.
            _, hist, elites = run_ga(spec, sc, pop_size, n_gen, seed=seed,
                                     adaptive=True, return_elites=ELITE_CARRY)
            carried_elites = elites
            rep_adaptive = [{"generation": r["generation"], "diversity": r["diversity"],
                             "mut_prob": r["mut_prob"]} for r in hist]
            target = hist[-1]["best"]
            per_day.append({"day": str(sc.timestamps[0].date()),
                            "gen_cold": generations_to_reach(hist, target),
                            "gen_warm": None,
                            "start_cold": round(hist[0]["best"], 2), "start_warm": None,
                            "best_cold": round(target, 2), "best_warm": None})
            continue

        # Baseline cold run for this day (fresh random population).
        _, hist_cold = run_ga(spec, sc, pop_size, n_gen, seed=seed, adaptive=True)
        # Warm run: seeded with yesterday's elites -- the actual closed loop.
        _, hist_warm, elites = run_ga(spec, sc, pop_size, n_gen, seed=seed,
                                      warm_start=carried_elites, adaptive=True,
                                      return_elites=ELITE_CARRY)
        carried_elites = elites

        # Fair comparison: how many generations each needs to reach the quality
        # the cold run ultimately achieves. Warm, seeded from yesterday's
        # elites, typically clears that bar at (or near) generation 0.
        target = hist_cold[-1]["best"]
        per_day.append({
            "day": str(sc.timestamps[0].date()),
            "gen_cold": generations_to_reach(hist_cold, target),
            "gen_warm": generations_to_reach(hist_warm, target),
            "start_cold": round(hist_cold[0]["best"], 2),
            "start_warm": round(hist_warm[0]["best"], 2),
            "best_cold": round(hist_cold[-1]["best"], 2),
            "best_warm": round(hist_warm[-1]["best"], 2),
        })
        if rep_curves is None:
            rep_curves = {
                "day": str(sc.timestamps[0].date()),
                "cold": [round(r["best"], 2) for r in hist_cold],
                "warm": [round(r["best"], 2) for r in hist_warm],
            }

    warm_days = [r for r in per_day if r["gen_warm"] is not None]
    mean_cold = float(np.mean([r["gen_cold"] for r in warm_days]))
    mean_warm = float(np.mean([r["gen_warm"] for r in warm_days]))
    reduction_pct = (mean_cold - mean_warm) / mean_cold * 100 if mean_cold else 0.0

    return {
        "per_day": per_day,
        "summary": {
            "mean_gen_cold": round(mean_cold, 1),
            "mean_gen_warm": round(mean_warm, 1),
            "reduction_pct": round(reduction_pct, 1),
            "elite_carry": ELITE_CARRY,
        },
        "convergence": rep_curves,
        "adaptive_trace": rep_adaptive,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5, help="consecutive test-season days to chain")
    ap.add_argument("--pop-size", type=int, default=POP_SIZE)
    ap.add_argument("--n-gen", type=int, default=N_GEN)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = run(args.days, args.pop_size, args.n_gen, seed=args.seed)

    s = out["summary"]
    print(f"Warm-starting over {args.days} days (carry {s['elite_carry']} elites):")
    for r in out["per_day"]:
        warm = "n/a" if r["gen_warm"] is None else str(r["gen_warm"])
        print(f"  {r['day']}: cold reaches target @gen {r['gen_cold']:>3}   warm @gen {warm:>3}")
    print(f"Mean generations to reach cold's converged quality: cold {s['mean_gen_cold']} -> "
          f"warm {s['mean_gen_warm']} ({s['reduction_pct']:+.1f}% "
          f"{'fewer' if s['reduction_pct'] > 0 else 'more'} generations)")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "learning.json").write_text(json.dumps(out))
    print(f"Wrote {RESULTS / 'learning.json'}")


if __name__ == "__main__":
    main()
