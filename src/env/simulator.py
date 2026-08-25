"""Plant model: ties generation, load, battery and grid together for one
simulated window (project plan section 7, `env/simulator.py`).

Scale note -- read this before changing any capacity number. The dataset
(plan section 6) is Germany's *national* grid: solar/wind/load are tens of
thousands of MW, far above anything a 300 kWh battery (`battery.py`) could
meaningfully affect. Rather than switch datasets (every alternative in
section 6.3 has worse access friction), each series is rescaled to a
per-unit fraction of its own historical peak and then multiplied by a chosen
microgrid nameplate capacity below. This preserves the real weather-driven
shape and cross-correlation of the national data -- which is what the
TFT/GA/PSO are actually evaluated on -- while bringing the numbers down to a
scale the battery can move the needle on. State this rescaling explicitly in
the report as a stand-in for genuine microgrid-scale generation data, which
was not freely available.

Sizing (deliberate, not arbitrary): the renewables are oversized relative to
load -- solar peak 450 kW and wind 250 kW against a 120 kW peak load -- so
that midday solar routinely exceeds demand and creates a genuine surplus for
the battery to store and shift into the evening peak. This is the defining
economic setup of a self-consumption microgrid; without it (an
import-dominated site) a battery has almost nothing to arbitrage and idle is
near-optimal. State the oversizing as a design choice in the report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.splits import load_splits

# Microgrid nameplate capacities (kW) the national per-unit profiles are
# rescaled to. Renewables oversized vs load on purpose (see module scale note)
# so the battery has a real surplus to store.
SOLAR_CAPACITY_KW = 450.0
WIND_CAPACITY_KW = 250.0
LOAD_PEAK_KW = 120.0

# Grid connection limits used by objective.py and milp_oracle.py. Set well
# above load so the (much larger) midday renewable surplus can export rather
# than being clipped into a penalty that would swamp the cost signal.
GRID_IMPORT_CAP_KW = 500.0
GRID_EXPORT_CAP_KW = 500.0

PRICE_FALLBACK_EUR_MWH = 40.0  # only used if a chosen window still has NaN price

# Retail import adder over the wholesale day-ahead price: network charges,
# taxes and levies paid on imported energy but not earned on exports. German
# retail is ~0.30 EUR/kWh vs ~0.05 wholesale; ~0.15 EUR/kWh (150 EUR/MWh) is a
# conservative commercial-microgrid adder. This import/export asymmetry is the
# main reason a self-consumption battery pays for itself (see objective.py).
IMPORT_ADDER_EUR_MWH = 150.0


@dataclass(frozen=True)
class Scenario:
    timestamps: pd.DatetimeIndex
    solar_kw: np.ndarray
    wind_kw: np.ndarray
    load_kw: np.ndarray
    price_eur_mwh: np.ndarray


_CAPACITY_KW = {"solar_mw": SOLAR_CAPACITY_KW, "wind_mw": WIND_CAPACITY_KW, "load_mw": LOAD_PEAK_KW}


def full_frame() -> pd.DataFrame:
    train, val, test = load_splits()
    return pd.concat([train, val, test]).sort_index()


def rescale(values_mw: np.ndarray, column: str, frame: pd.DataFrame | None = None) -> np.ndarray:
    """Rescale a raw-MW series (actual or forecast, same units as `column`)
    into microgrid kW, using that column's own historical peak as the
    per-unit base -- see the module scale note. Exposed publicly (not just
    used inside build_scenario) so the TFT's forecast values can be rescaled
    identically to actuals -- see pso_refiner.py, which needs both on a
    comparable footing."""
    df = full_frame() if frame is None else frame
    peak = df[column].max()
    return (np.asarray(values_mw, dtype=float) / peak) * _CAPACITY_KW[column]


def build_scenario(start, hours: int, frame: pd.DataFrame | None = None) -> Scenario:
    """Rescaled (solar, wind, load, price) window of `hours` hours from `start`."""
    df = full_frame() if frame is None else frame
    window = df.loc[pd.Timestamp(start):].iloc[:hours]
    if len(window) < hours:
        raise ValueError(f"Only {len(window)} rows available from {start}, need {hours}")

    price = window["price_eur_mwh"].fillna(PRICE_FALLBACK_EUR_MWH).to_numpy()

    return Scenario(
        timestamps=window.index,
        solar_kw=rescale(window["solar_mw"].to_numpy(), "solar_mw", df),
        wind_kw=rescale(window["wind_mw"].to_numpy(), "wind_mw", df),
        load_kw=rescale(window["load_mw"].to_numpy(), "load_mw", df),
        price_eur_mwh=price,
    )


def test_window(hours: int = 24 * 7, offset_hours: int = 0) -> Scenario:
    """A window drawn from the test split (held out of TFT training/
    validation), for evaluating dispatch policies consistently. `offset_hours`
    shifts the start later into the test set (e.g. to skip a partial first day).
    """
    _, _, test = load_splits()
    full = full_frame()
    start = test.index[0] + pd.Timedelta(hours=offset_hours)
    return build_scenario(start, hours, frame=full)


if __name__ == "__main__":
    sc = test_window(24)
    print(f"window: {sc.timestamps[0]} -> {sc.timestamps[-1]}")
    print(f"solar kw: min={sc.solar_kw.min():.1f} max={sc.solar_kw.max():.1f}")
    print(f"wind  kw: min={sc.wind_kw.min():.1f} max={sc.wind_kw.max():.1f}")
    print(f"load  kw: min={sc.load_kw.min():.1f} max={sc.load_kw.max():.1f}")
    print(f"price eur/mwh: min={sc.price_eur_mwh.min():.1f} max={sc.price_eur_mwh.max():.1f}")
