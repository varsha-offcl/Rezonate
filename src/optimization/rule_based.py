"""Rule-based heuristic dispatch -- the performance floor row in the
evaluation table (project plan section 12). No optimisation and no
foresight; purely reactive: charge on a renewable surplus, discharge to
cover a deficit, clipped to the battery's power rating and SOC band.
"""

from __future__ import annotations

import numpy as np

from src.env.battery import BatterySpec, step_soc


def dispatch(solar_kw: np.ndarray, wind_kw: np.ndarray, load_kw: np.ndarray,
             spec: BatterySpec, dt_h: float = 1.0) -> np.ndarray:
    n = len(load_kw)
    power = np.empty(n)
    soc = spec.soc_init
    for t in range(n):
        net = solar_kw[t] + wind_kw[t] - load_kw[t]  # >0 surplus, <0 deficit
        # objective.py convention: +power = discharge, -power = charge. So a
        # surplus (net>0) must map to CHARGING (negative power) and a deficit
        # to DISCHARGING (positive power) -- hence -net, not net.
        p = float(np.clip(-net, -spec.max_power_kw, spec.max_power_kw))

        if p < 0:  # would charge -- cap to remaining headroom below soc_max
            headroom_kwh = (spec.soc_max - soc) * spec.capacity_kwh
            max_charge_kw = headroom_kwh / (spec.eta_charge * dt_h)
            p = max(p, -max_charge_kw)
        elif p > 0:  # would discharge -- cap to remaining headroom above soc_min
            headroom_kwh = (soc - spec.soc_min) * spec.capacity_kwh
            max_discharge_kw = headroom_kwh * spec.eta_discharge / dt_h
            p = min(p, max_discharge_kw)

        power[t] = p
        soc = step_soc(soc, p, spec, dt_h)
    return power


if __name__ == "__main__":
    from src.env.objective import evaluate
    from src.env.simulator import test_window

    spec = BatterySpec()
    sc = test_window(24 * 7)
    power = dispatch(sc.solar_kw, sc.wind_kw, sc.load_kw, spec)
    result = evaluate(power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    print(f"rule-based week cost: EUR {result['total_cost']:.2f} "
          f"(import={result['import_cost']:.2f} export=-{result['export_revenue']:.2f} "
          f"deg={result['degradation_cost']:.2f} penalties={result['penalties']:.2f})")
