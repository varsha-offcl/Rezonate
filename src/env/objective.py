"""Objective function (project plan section 4):

    J = sum[import_cost - export_revenue] + degradation_cost + constraint_penalties

Penalties are soft (the simulator itself always produces a feasible SOC
trajectory), but a GA/PSO candidate in later phases may propose an infeasible
schedule, so violations are priced here rather than only clipped -- that
price is what steers the optimiser back toward feasibility. The terminal-SOC
penalty exists specifically because, without it, the optimiser drains the
battery on the final interval and reports savings that are not real -- the
plan (section 4) flags this as the most common bug in this class of project.
"""

from __future__ import annotations

import numpy as np

from src.env.battery import BatterySpec, degradation_cost, soc_trajectory
from src.env.simulator import GRID_EXPORT_CAP_KW, GRID_IMPORT_CAP_KW, IMPORT_ADDER_EUR_MWH

# Penalties price genuine physical infeasibility (a GA/PSO candidate proposing
# an impossible schedule); a feasible schedule incurs none. Terminal SOC is
# handled as an economic settlement in evaluate(), not priced here.
POWER_VIOLATION_PENALTY_EUR = 1000.0  # per kW over the battery's rating
SOC_VIOLATION_PENALTY_EUR = 5000.0  # per unit-hour of SOC out of bounds
GRID_VIOLATION_PENALTY_EUR = 1000.0  # per kW over the grid connection cap


def evaluate(
    battery_power_kw: np.ndarray,
    solar_kw: np.ndarray,
    wind_kw: np.ndarray,
    load_kw: np.ndarray,
    price_eur_mwh: np.ndarray,
    spec: BatterySpec,
    dt_h: float = 1.0,
) -> dict:
    """Cost breakdown for one battery power schedule against one weather/
    load/price scenario. Positive `battery_power_kw` = discharging (adds to
    supply); negative = charging (adds to demand) -- matches the plan's
    schedule-chart convention (charge below axis, discharge above).
    """
    net_generation_kw = solar_kw + wind_kw + battery_power_kw - load_kw
    grid_kw = -net_generation_kw  # >0 import, <0 export
    import_kw = np.clip(grid_kw, 0, None)
    export_kw = np.clip(-grid_kw, 0, None)

    # Import/export price asymmetry -- the dominant driver of behind-the-meter
    # battery economics. You buy at retail (wholesale day-ahead price + network
    # charges, taxes, levies) but sell surplus at wholesale. That gap is what
    # makes storing your own solar for the evening worth more than exporting it
    # cheap and re-importing dear; with a single price the battery is nearly
    # worthless. See simulator.IMPORT_ADDER_EUR_MWH.
    import_price_eur_kwh = (price_eur_mwh + IMPORT_ADDER_EUR_MWH) / 1000.0
    export_price_eur_kwh = price_eur_mwh / 1000.0
    import_cost = float(np.sum(import_kw * dt_h * import_price_eur_kwh))
    export_revenue = float(np.sum(export_kw * dt_h * export_price_eur_kwh))

    soc = soc_trajectory(battery_power_kw, spec, dt_h)
    deg_cost = degradation_cost(soc, spec)

    penalties = 0.0
    power_over = np.clip(np.abs(battery_power_kw) - spec.max_power_kw, 0, None)
    penalties += POWER_VIOLATION_PENALTY_EUR * float(np.sum(power_over))

    soc_under = np.clip(spec.soc_min - soc, 0, None)
    soc_over = np.clip(soc - spec.soc_max, 0, None)
    penalties += SOC_VIOLATION_PENALTY_EUR * float(np.sum(soc_under) + np.sum(soc_over))

    grid_over = (float(np.clip(import_kw - GRID_IMPORT_CAP_KW, 0, None).sum())
                 + float(np.clip(export_kw - GRID_EXPORT_CAP_KW, 0, None).sum()))
    penalties += GRID_VIOLATION_PENALTY_EUR * grid_over

    # Terminal-SOC settlement (not a penalty): a schedule that ends below its
    # starting charge has effectively borrowed energy it must buy back at
    # import price to return to the start state. Ending ABOVE start must be
    # credited at the (lower) EXPORT price, not import -- crediting a surplus
    # at import price is a real exploit: it lets a policy "sell" stored energy
    # to itself at a price it could never actually realise (the ablation's
    # oracle-is-a-ceiling invariant caught exactly this, since the oracle is
    # honestly locked to zero settlement every day while an unconstrained
    # policy could bank a fictitious credit by getting lucky on ending SOC).
    # This asymmetric settlement closes the "drain the battery for fake
    # savings" exploit (plan section 4) without opening the mirror-image one.
    mean_import_price_eur_kwh = float(np.mean(price_eur_mwh + IMPORT_ADDER_EUR_MWH)) / 1000.0
    mean_export_price_eur_kwh = float(np.mean(price_eur_mwh)) / 1000.0
    terminal_gap_kwh = (spec.soc_init - soc[-1]) * spec.capacity_kwh  # >0 deficit, <0 surplus
    settlement_price = mean_import_price_eur_kwh if terminal_gap_kwh > 0 else mean_export_price_eur_kwh
    terminal_settlement = terminal_gap_kwh * settlement_price

    total_cost = import_cost - export_revenue + deg_cost + terminal_settlement + penalties

    return {
        "total_cost": total_cost,
        "import_cost": import_cost,
        "export_revenue": export_revenue,
        "degradation_cost": deg_cost,
        "terminal_settlement": round(terminal_settlement, 4),
        "penalties": penalties,
        "import_kwh": float(np.sum(import_kw * dt_h)),
        "export_kwh": float(np.sum(export_kw * dt_h)),
        "soc": soc,
        "import_kw": import_kw,
        "export_kw": export_kw,
    }


if __name__ == "__main__":
    from src.env.simulator import test_window

    spec = BatterySpec()
    sc = test_window(24)
    # Do-nothing baseline: battery idle all day.
    idle = np.zeros(len(sc.load_kw))
    result = evaluate(idle, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    print(f"idle-battery day cost: EUR {result['total_cost']:.2f} "
          f"(import={result['import_cost']:.2f} export=-{result['export_revenue']:.2f} "
          f"deg={result['degradation_cost']:.2f} penalties={result['penalties']:.2f})")
