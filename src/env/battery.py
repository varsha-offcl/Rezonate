"""Battery model: SOC dynamics + rainflow-counted cycle degradation cost
(project plan section 4).

Nameplate spec (documented assumption -- everything is simulated, no
hardware -- chosen to be a coherent community-scale LFP system sized so the
battery has a real economic job against the microgrid's renewable surplus,
see src/env/simulator.py's scale note):
  capacity   300 kWh usable (~2.5h at peak load)
  power      100 kW max charge/discharge (0.33C)
  efficiency 90% round-trip, split symmetrically as sqrt(0.9) per direction
  SOC bounds 20%-90% (project plan section 4 constraint)
  capital    75,000 EUR (~250 EUR/kWh, representative LFP pack price)

Degradation: rainflow cycle counting (the `rainflow` package) on the SOC
trajectory, then the power-law cycles-to-failure curve from the plan
(section 4):
    N_fail(d) = a * d^(-b)              d = cycle depth, fraction of capacity
    cost_per_cycle(d) = capital_cost / (2 * N_fail(d))

degradation_a / degradation_b are a least-squares power-law fit to published
cycle-life-vs-DOD datasheet figures for a representative LFP prismatic cell
(EVE/CATL-class): ~3000 full cycles at 100% DOD, ~6000 at 80%, ~8000 at 70%,
all to 80%-capacity end-of-life. The fit reproduces those points to within a
few percent (a=3059 => N_fail(100% DOD)=3059). Cite these datasheet figures
in the report; if you adopt a specific named cell, re-fit to its numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rainflow


@dataclass(frozen=True)
class BatterySpec:
    capacity_kwh: float = 300.0
    max_power_kw: float = 100.0
    eta_charge: float = 0.9487  # sqrt(0.90), one-way efficiency
    eta_discharge: float = 0.9487
    soc_min: float = 0.20
    soc_max: float = 0.90
    soc_init: float = 0.55
    capital_cost_eur: float = 75_000.0  # pack replacement cost, ~250 EUR/kWh
    # Power-law fit to LFP datasheet cycle life vs DOD (see module docstring).
    degradation_a: float = 3059.0
    degradation_b: float = 2.786


def step_soc(soc: float, power_kw: float, spec: BatterySpec, dt_h: float = 1.0) -> float:
    """SOC after one interval at constant power (kW, +discharge / -charge).

    Efficiency losses are always paid by the battery: a discharge interval
    pulls more energy out of the cell than reaches the bus; a charge
    interval puts less energy into the cell than is drawn from the bus.
    """
    if power_kw >= 0:
        delta_kwh = -(power_kw * dt_h) / spec.eta_discharge
    else:
        delta_kwh = -(power_kw * dt_h) * spec.eta_charge
    return soc + delta_kwh / spec.capacity_kwh


def soc_trajectory(power_kw: np.ndarray, spec: BatterySpec, dt_h: float = 1.0) -> np.ndarray:
    """SOC after each interval. Returned array has length len(power_kw)+1;
    soc[0] is the initial SOC."""
    n = len(power_kw)
    soc = np.empty(n + 1)
    soc[0] = spec.soc_init
    for t in range(n):
        soc[t + 1] = step_soc(soc[t], power_kw[t], spec, dt_h)
    return soc


def n_fail(d: float, spec: BatterySpec) -> float:
    """Cycles to failure at depth-of-discharge `d` (fraction of capacity)."""
    return spec.degradation_a * d ** (-spec.degradation_b)


def marginal_cost_per_kwh(d: float, spec: BatterySpec) -> float:
    """Closed-form marginal wear cost (EUR/kWh throughput) at depth `d`.

    Derived from cost(d) = capital_cost * d^b / (2a) and
    throughput(d) = 2 * capacity_kwh * d (one charge + one discharge of
    depth d), so d(cost)/d(throughput) = capital_cost*b*d^(b-1) / (4*a*capacity).
    Used by the MILP oracle's piecewise-linear degradation proxy.
    """
    return (spec.capital_cost_eur * spec.degradation_b * d ** (spec.degradation_b - 1)
            / (4 * spec.degradation_a * spec.capacity_kwh))


def degradation_cost(soc: np.ndarray, spec: BatterySpec) -> float:
    """Total degradation cost (EUR) for a SOC trajectory via rainflow counting.

    Each rainflow-extracted cycle (full or half) of depth `d` consumes
    `count / (2 * N_fail(d))` of the pack's remaining life -- the factor of 2
    because N_fail already counts full cycles to failure and a half-cycle
    uses half a full cycle's worth of life. This is nonconvex/non-
    differentiable in the dispatch schedule (plan section 4) -- the reason
    the MILP oracle instead uses the linear proxy above.
    """
    total = 0.0
    for rng, _mean, count, *_ in rainflow.extract_cycles(soc):
        d = rng  # soc is already a 0-1 fraction, so range == depth of discharge
        if d <= 0:
            continue
        total += spec.capital_cost_eur * count / (2.0 * n_fail(d, spec))
    return total


if __name__ == "__main__":
    spec = BatterySpec()
    # One shallow round trip: 1h discharge at 20kW, 1h charge at 20kW back.
    power = np.array([20.0, -20.0])
    soc = soc_trajectory(power, spec)
    print("soc trajectory:", np.round(soc, 4), "(round-trip loss visible in soc[0] vs soc[-1])")
    print("degradation cost (EUR):", round(degradation_cost(soc, spec), 4))
    print("marginal cost @ d=0.15 (EUR/kWh):", round(marginal_cost_per_kwh(0.15, spec), 4))
    print("marginal cost @ d=0.70 (EUR/kWh):", round(marginal_cost_per_kwh(0.70, spec), 4))
