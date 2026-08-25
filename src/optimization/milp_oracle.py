"""Perfect-foresight oracle (project plan section 7 `optimization/milp_oracle.py`,
phase detail section 11 Phase 3).

Solver: **PuLP + CBC**, bundled and license-free -- pinned in the plan
(sections 5, 11); Pyomo is deliberately avoided since its tutorials default
toward commercial solvers.

Design note -- no binary variables needed. Charge and discharge are each
split into two non-negative "tiers" per interval (shallow / deep), priced at
increasing marginal cost (below). Minimising a convex, increasing-marginal-
cost objective always fills the cheaper tier before the more expensive one,
which reproduces a genuine charge-or-discharge split without a simultaneous-
charge-and-discharge binary indicator. The whole problem stays a pure LP,
which is what "MILP oracle" reduces to here.

Degradation treatment -- the decision the plan asks this phase to make
(section 11): a **piecewise-linear proxy**, not "no degradation" (which
would understate the real system) and not the exact rainflow cost (which is
nonconvex/non-differentiable and not LP-representable -- the plan's own
justification, section 4, for using metaheuristics at all). The proxy comes
from the closed form in `battery.py`:

    marginal cost per kWh throughput at depth d = capital_cost * b * d^(b-1)
                                                   / (4 * a * capacity_kwh)

Two tiers per direction approximate this convex curve: a "shallow" rate
priced at depth D_LO, and a "deep" rate priced at the largest feasible
single-interval depth, with the shallow tier's capacity capped at the
throughput D_LO represents.

After solving, the oracle's own battery-power trajectory is re-scored with
the *exact* rainflow-based degradation cost from `battery.py` via
`objective.evaluate`. The gap between the LP's linearized cost and that true
nonlinear cost is exactly what plan section 3 calls "the strongest available
defence of using metaheuristics": it quantifies what the LP relaxation's
linearity assumption loses.

Run:
  .venv/Scripts/python -m src.optimization.milp_oracle --hours 168
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pulp

from src.env.battery import BatterySpec, marginal_cost_per_kwh
from src.env.objective import evaluate
from src.env.simulator import (
    GRID_EXPORT_CAP_KW,
    GRID_IMPORT_CAP_KW,
    IMPORT_ADDER_EUR_MWH,
    test_window,
)

D_LO = 0.15  # shallow-cycle depth used to price the cheap tier


def solve(solar_kw, wind_kw, load_kw, price_eur_mwh, spec: BatterySpec, dt_h: float = 1.0) -> dict:
    T = len(load_kw)
    d_hi = spec.soc_max - spec.soc_min  # deepest single-interval swing physically possible

    rate_lo = marginal_cost_per_kwh(D_LO, spec)
    rate_hi = marginal_cost_per_kwh(d_hi, spec)
    tier1_cap_kw = min(spec.max_power_kw, D_LO * spec.capacity_kwh / dt_h)
    tier2_cap_kw = spec.max_power_kw - tier1_cap_kw

    prob = pulp.LpProblem("microgrid_oracle", pulp.LpMinimize)

    ch1 = [pulp.LpVariable(f"ch1_{t}", 0, tier1_cap_kw) for t in range(T)]
    ch2 = [pulp.LpVariable(f"ch2_{t}", 0, tier2_cap_kw) for t in range(T)]
    dis1 = [pulp.LpVariable(f"dis1_{t}", 0, tier1_cap_kw) for t in range(T)]
    dis2 = [pulp.LpVariable(f"dis2_{t}", 0, tier2_cap_kw) for t in range(T)]
    imp = [pulp.LpVariable(f"imp_{t}", 0, GRID_IMPORT_CAP_KW) for t in range(T)]
    exp = [pulp.LpVariable(f"exp_{t}", 0, GRID_EXPORT_CAP_KW) for t in range(T)]
    soc = [pulp.LpVariable(f"soc_{t}", spec.soc_min, spec.soc_max) for t in range(T + 1)]
    # Binary charge/discharge indicator -- this is what makes it a MILP, not an
    # LP. Without it the solver may charge AND discharge in the same interval,
    # which is unphysical and (because the objective prices charge/discharge
    # separately) makes the linearized SOC path disagree with the true
    # net-power simulation in objective.evaluate -- the oracle then breaches the
    # SOC cap when re-scored and stops being a valid ceiling. is_charging=1
    # forces discharge to 0 that hour, and vice-versa.
    is_charging = [pulp.LpVariable(f"chg_{t}", cat="Binary") for t in range(T)]

    prob += soc[0] == spec.soc_init
    prob += soc[T] == spec.soc_init  # terminal SOC -- plan section 4's flagged bug otherwise

    for t in range(T):
        charge_kw = ch1[t] + ch2[t]
        discharge_kw = dis1[t] + dis2[t]
        prob += soc[t + 1] == soc[t] + (charge_kw * spec.eta_charge * dt_h
                                         - discharge_kw * dt_h / spec.eta_discharge) / spec.capacity_kwh
        prob += (solar_kw[t] + wind_kw[t] + discharge_kw - charge_kw + imp[t] - exp[t]
                 == load_kw[t])
        # Mutual exclusion: charge only when is_charging=1, discharge only when =0.
        prob += charge_kw <= spec.max_power_kw * is_charging[t]
        prob += discharge_kw <= spec.max_power_kw * (1 - is_charging[t])

    # Import/export price asymmetry -- must match objective.evaluate exactly, or
    # the oracle optimises a different cost than it's scored against.
    import_price_kwh = (price_eur_mwh + IMPORT_ADDER_EUR_MWH) / 1000.0
    export_price_kwh = price_eur_mwh / 1000.0
    degradation_terms = [
        rate_lo * dt_h * (ch1[t] + dis1[t]) + rate_hi * dt_h * (ch2[t] + dis2[t])
        for t in range(T)
    ]
    prob += (pulp.lpSum(imp[t] * dt_h * float(import_price_kwh[t]) for t in range(T))
             - pulp.lpSum(exp[t] * dt_h * float(export_price_kwh[t]) for t in range(T))
             + pulp.lpSum(degradation_terms))

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

    battery_power_kw = np.array([
        (dis1[t].value() + dis2[t].value()) - (ch1[t].value() + ch2[t].value())
        for t in range(T)
    ])
    return {
        "status": pulp.LpStatus[status],
        "battery_power_kw": battery_power_kw,
        "linearized_cost": pulp.value(prob.objective),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=168, help="window length, hours (default: one week)")
    args = ap.parse_args()

    spec = BatterySpec()
    sc = test_window(args.hours)

    t0 = time.time()
    result = solve(sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    elapsed = time.time() - t0

    true_cost = evaluate(result["battery_power_kw"], sc.solar_kw, sc.wind_kw, sc.load_kw,
                          sc.price_eur_mwh, spec)

    print(f"status: {result['status']}  solved in {elapsed:.2f}s over {args.hours}h")
    print(f"linearized (LP) cost:  EUR {result['linearized_cost']:.2f}")
    print(f"true nonlinear cost:   EUR {true_cost['total_cost']:.2f}  "
          f"(gap: {true_cost['total_cost'] - result['linearized_cost']:.2f})")
    print(f"  import={true_cost['import_cost']:.2f} export=-{true_cost['export_revenue']:.2f} "
          f"deg={true_cost['degradation_cost']:.2f} penalties={true_cost['penalties']:.2f}")


if __name__ == "__main__":
    main()
