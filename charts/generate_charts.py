"""
Standalone chart generator for the teacher deliverable — V-I / P-V curves plus
dataset trend charts. Lives entirely outside `src/`, only *reads*
`data/processed/merged.parquet` (never modifies it), and writes PNGs into
`teacher_charts/figures/`. Does not touch anything in the main codebase.

IMPORTANT CONTEXT: the project's dataset (`data/processed/merged.parquet`) is
grid-scale hourly power (MW) for solar/wind/load plus weather — it has no
per-panel voltage/current measurements, so a real V-I curve can't be read off
it directly. The V-I and P-V curves below are instead generated from a
standard single-diode PV-cell model (the textbook approach used to produce
these curves for any panel), driven at STC and swept over irradiance/
temperature. The last PV chart drives that same model with the dataset's own
*real* irradiance + temperature readings for one summer day, tying the two
parts together.

Run (from repo root, venv already set up):
    .venv/Scripts/python teacher_charts/generate_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "merged.parquet"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 110,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 10,
})

# ---------------------------------------------------------------------------
# Part A — trend charts from the real dataset
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    df = pd.read_parquet(DATA)
    df.index = pd.to_datetime(df.index)
    return df


def chart_monthly_generation_trend(df: pd.DataFrame):
    monthly = df[["solar_mw", "wind_mw", "load_mw"]].resample("MS").mean()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(monthly.index, monthly["solar_mw"], label="Solar (MW, monthly mean)")
    ax.plot(monthly.index, monthly["wind_mw"], label="Wind (MW, monthly mean)")
    ax.plot(monthly.index, monthly["load_mw"], label="Load (MW, monthly mean)", alpha=0.6)
    ax.set_title("Monthly mean generation & load, 2016–2020")
    ax.set_xlabel("Month")
    ax.set_ylabel("MW")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "01_trend_monthly_generation.png")
    plt.close(fig)


def chart_seasonal_profile(df: pd.DataFrame):
    by_month = df.groupby(df.index.month)[["solar_mw", "wind_mw", "load_mw"]].mean()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(months, by_month["solar_mw"], marker="o", label="Solar")
    ax.plot(months, by_month["wind_mw"], marker="o", label="Wind")
    ax.plot(months, by_month["load_mw"], marker="o", label="Load", alpha=0.6)
    ax.set_title("Average seasonal profile (mean by calendar month, all years pooled)")
    ax.set_ylabel("MW")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "02_trend_seasonal_profile.png")
    plt.close(fig)


def chart_diurnal_profile(df: pd.DataFrame):
    by_hour = df.groupby(df.index.hour)[["solar_mw", "wind_mw", "load_mw"]].mean()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(by_hour.index, by_hour["solar_mw"], marker="o", label="Solar")
    ax.plot(by_hour.index, by_hour["wind_mw"], marker="o", label="Wind")
    ax.plot(by_hour.index, by_hour["load_mw"], marker="o", label="Load", alpha=0.6)
    ax.set_title("Average diurnal profile (mean by hour-of-day, all days pooled)")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("MW")
    ax.set_xticks(range(0, 24, 2))
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "03_trend_diurnal_profile.png")
    plt.close(fig)


def chart_price_trend(df: pd.DataFrame):
    # price only exists from 2018-10-01 onward (DE/AT/LU bidding-zone split, see data/NOTES.md)
    price = df["price_eur_mwh"].dropna().resample("D").mean()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(price.index, price.values, linewidth=0.8)
    ax.plot(price.index, price.rolling(30).mean(), linewidth=2, label="30-day rolling mean")
    ax.set_title("Day-ahead price trend (daily mean, EUR/MWh)")
    ax.set_ylabel("EUR/MWh")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "04_trend_price.png")
    plt.close(fig)


def chart_correlations(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    sample = df.sample(min(4000, len(df)), random_state=42)
    axes[0].scatter(sample["shortwave_radiation"], sample["solar_mw"], s=4, alpha=0.3)
    axes[0].set_xlabel("Shortwave radiation (W/m²)")
    axes[0].set_ylabel("Solar generation (MW)")
    axes[0].set_title("Solar output vs irradiance")

    axes[1].scatter(sample["windspeed_100m"], sample["wind_mw"], s=4, alpha=0.3, color="darkorange")
    axes[1].set_xlabel("Wind speed @ 100m (km/h)")
    axes[1].set_ylabel("Wind generation (MW)")
    axes[1].set_title("Wind output vs wind speed")

    fig.tight_layout()
    fig.savefig(OUT / "05_trend_correlations.png")
    plt.close(fig)


def chart_distributions(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, col, title in zip(
        axes, ["solar_mw", "wind_mw", "load_mw"], ["Solar (MW)", "Wind (MW)", "Load (MW)"]
    ):
        ax.hist(df[col].dropna(), bins=60, color="steelblue")
        ax.set_title(title)
    fig.suptitle("Distribution of hourly generation / load, 2016–2020")
    fig.tight_layout()
    fig.savefig(OUT / "06_dist_generation_load.png")
    plt.close(fig)


def chart_capacity_factor_trend(df: pd.DataFrame):
    # normalises out capacity growth over the years -> shows the underlying
    # resource-utilisation trend, not just installed-capacity growth
    cf = pd.DataFrame(index=df.index)
    cf["solar_cf"] = (df["solar_mw"] / df["solar_capacity_mw"]).clip(0, 1)
    cf["wind_cf"] = (df["wind_mw"] / df["wind_capacity_mw"]).clip(0, 1)
    cf = cf.rolling("30D").mean()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(cf.index, cf["solar_cf"], label="Solar capacity factor (30d rolling)")
    ax.plot(cf.index, cf["wind_cf"], label="Wind capacity factor (30d rolling)")
    ax.set_title("Capacity factor trend (generation ÷ installed capacity)")
    ax.set_ylabel("Capacity factor")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "07_trend_capacity_factor.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Part B — PV single-diode model: V-I and P-V characteristic curves
# ---------------------------------------------------------------------------
# Standard 5-parameter single-diode equivalent circuit for a silicon PV
# module, evaluated at STC and adjusted for irradiance/temperature with the
# usual textbook relations. Nameplate numbers below are representative of a
# generic ~250W polycrystalline module (STC: 1000 W/m^2, 25C, AM1.5).

Q = 1.602176634e-19       # electron charge, C
K = 1.380649e-23          # Boltzmann constant, J/K
NS = 60                   # cells in series
N_IDEAL = 1.3              # diode ideality factor
RS = 0.35                 # series resistance, ohm
RSH = 300.0                # shunt resistance, ohm
EG_EV = 1.121               # silicon bandgap, eV

G_STC = 1000.0              # W/m^2
T_STC_C = 25.0
ALPHA_ISC = 0.0005          # Isc temp coeff, per degC (~0.05%/C)

ISC_STC = 8.8               # A
VOC_STC = 37.5               # V


def thermal_voltage(temp_c: float) -> float:
    t_k = temp_c + 273.15
    return K * t_k / Q


def i0_stc() -> float:
    vt = thermal_voltage(T_STC_C)
    return ISC_STC / (np.exp(VOC_STC / (NS * N_IDEAL * vt)) - 1)


I0_STC = i0_stc()


def diode_params(irradiance: float, temp_c: float):
    """Return (Iph, I0, Vt) for given irradiance (W/m^2) and cell temp (degC)."""
    t_k = temp_c + 273.15
    t_stc_k = T_STC_C + 273.15
    iph = (irradiance / G_STC) * (ISC_STC + ALPHA_ISC * (temp_c - T_STC_C))
    i0 = I0_STC * (t_k / t_stc_k) ** 3 * np.exp(
        (EG_EV * Q / (N_IDEAL * K)) * (1 / t_stc_k - 1 / t_k)
    )
    vt = thermal_voltage(temp_c)
    return iph, i0, vt


def iv_curve(irradiance: float, temp_c: float, n_points: int = 200):
    """Solve the single-diode equation for I(V) via Newton-Raphson, vectorised
    over a voltage sweep. Returns (V, I) arrays, V from 0 to Voc."""
    iph, i0, vt = diode_params(irradiance, temp_c)
    if iph <= 0:
        v = np.linspace(0, VOC_STC, n_points)
        return v, np.zeros_like(v)

    # open-circuit voltage for this condition (I=0), via 1D Newton-Raphson
    voc = VOC_STC
    for _ in range(100):
        exp_term = np.exp(voc / (NS * N_IDEAL * vt))
        f = iph - i0 * (exp_term - 1) - voc / RSH
        fprime = -i0 * exp_term / (NS * N_IDEAL * vt) - 1 / RSH
        voc = voc - f / fprime

    v = np.linspace(0, max(voc, 0.01), n_points)
    i = np.full_like(v, iph)
    for _ in range(60):
        exp_term = np.exp((v + i * RS) / (NS * N_IDEAL * vt))
        f = iph - i0 * (exp_term - 1) - (v + i * RS) / RSH - i
        fprime = -i0 * (RS / (NS * N_IDEAL * vt)) * exp_term - RS / RSH - 1
        i = i - f / fprime
        i = np.clip(i, 0, None)
    return v, i


def chart_iv_pv_vs_irradiance():
    temp_c = 25.0
    irr_levels = [200, 400, 600, 800, 1000]

    fig_iv, ax_iv = plt.subplots(figsize=(8, 6))
    fig_pv, ax_pv = plt.subplots(figsize=(8, 6))
    for g in irr_levels:
        v, i = iv_curve(g, temp_c)
        p = v * i
        ax_iv.plot(v, i, label=f"{g} W/m²")
        ax_pv.plot(v, p, label=f"{g} W/m²")
        mpp = np.argmax(p)
        ax_pv.plot(v[mpp], p[mpp], "ko", markersize=3)

    ax_iv.set_title(f"I-V characteristic vs irradiance (T = {temp_c:.0f}°C)")
    ax_iv.set_xlabel("Voltage (V)")
    ax_iv.set_ylabel("Current (A)")
    ax_iv.legend(title="Irradiance")
    fig_iv.tight_layout()
    fig_iv.savefig(OUT / "08_pv_iv_curves_irradiance.png")
    plt.close(fig_iv)

    ax_pv.set_title(f"P-V characteristic vs irradiance (T = {temp_c:.0f}°C, dots = MPP)")
    ax_pv.set_xlabel("Voltage (V)")
    ax_pv.set_ylabel("Power (W)")
    ax_pv.legend(title="Irradiance")
    fig_pv.tight_layout()
    fig_pv.savefig(OUT / "09_pv_pv_curves_irradiance.png")
    plt.close(fig_pv)


def chart_iv_pv_vs_temperature():
    irradiance = 1000.0
    temps = [0, 25, 50, 75]

    fig_iv, ax_iv = plt.subplots(figsize=(8, 6))
    fig_pv, ax_pv = plt.subplots(figsize=(8, 6))
    for t in temps:
        v, i = iv_curve(irradiance, t)
        p = v * i
        ax_iv.plot(v, i, label=f"{t}°C")
        ax_pv.plot(v, p, label=f"{t}°C")
        mpp = np.argmax(p)
        ax_pv.plot(v[mpp], p[mpp], "ko", markersize=3)

    ax_iv.set_title(f"I-V characteristic vs temperature (G = {irradiance:.0f} W/m²)")
    ax_iv.set_xlabel("Voltage (V)")
    ax_iv.set_ylabel("Current (A)")
    ax_iv.legend(title="Temperature")
    fig_iv.tight_layout()
    fig_iv.savefig(OUT / "10_pv_iv_curves_temperature.png")
    plt.close(fig_iv)

    ax_pv.set_title(f"P-V characteristic vs temperature (G = {irradiance:.0f} W/m², dots = MPP)")
    ax_pv.set_xlabel("Voltage (V)")
    ax_pv.set_ylabel("Power (W)")
    ax_pv.legend(title="Temperature")
    fig_pv.tight_layout()
    fig_pv.savefig(OUT / "11_pv_pv_curves_temperature.png")
    plt.close(fig_pv)


def chart_pv_curve_from_dataset_day(df: pd.DataFrame, day: str = "2019-06-21"):
    """Drives the same PV model with *real* irradiance + temperature readings
    from the dataset for several hours of one summer day -- ties the physics
    model to the actual data."""
    day_df = df.loc[day]
    hours = [6, 9, 12, 15, 18]
    hours = [h for h in hours if h in day_df.index.hour.tolist()]

    fig, (ax_iv, ax_pv) = plt.subplots(1, 2, figsize=(13, 5.5))
    for h in hours:
        row = day_df[day_df.index.hour == h].iloc[0]
        g, t = float(row["shortwave_radiation"]), float(row["temperature_2m"])
        v, i = iv_curve(max(g, 1e-6), t)
        p = v * i
        label = f"{h:02d}:00  (G={g:.0f} W/m², T={t:.1f}°C)"
        ax_iv.plot(v, i, label=label)
        ax_pv.plot(v, p, label=label)

    ax_iv.set_title(f"I-V curve at real dataset conditions — {day}")
    ax_iv.set_xlabel("Voltage (V)")
    ax_iv.set_ylabel("Current (A)")
    ax_iv.legend(fontsize=8)

    ax_pv.set_title(f"P-V curve at real dataset conditions — {day}")
    ax_pv.set_xlabel("Voltage (V)")
    ax_pv.set_ylabel("Power (W)")
    ax_pv.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT / "12_pv_curve_dataset_day.png")
    plt.close(fig)


def main():
    df = load_data()

    chart_monthly_generation_trend(df)
    chart_seasonal_profile(df)
    chart_diurnal_profile(df)
    chart_price_trend(df)
    chart_correlations(df)
    chart_distributions(df)
    chart_capacity_factor_trend(df)

    chart_iv_pv_vs_irradiance()
    chart_iv_pv_vs_temperature()
    chart_pv_curve_from_dataset_day(df)

    print(f"Wrote {len(list(OUT.glob('*.png')))} charts to {OUT}")


if __name__ == "__main__":
    main()
