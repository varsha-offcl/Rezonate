"""Data-quality inspection: plot every series, check for gaps, DST
discontinuities, zero-runs and implausible values. Saves PNGs to
results/figures/ and prints a summary used to write data/NOTES.md.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MERGED_PATH = ROOT / "data" / "processed" / "merged.parquet"
FIG_DIR = ROOT / "results" / "figures"

SERIES = [
    "solar_mw", "wind_mw", "load_mw", "load_forecast_tso_mw", "price_eur_mwh",
    "shortwave_radiation", "direct_radiation", "temperature_2m",
    "cloudcover", "windspeed_100m",
]


def plot_full_series(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(len(SERIES), 1, figsize=(14, 2.2 * len(SERIES)), sharex=True)
    for ax, col in zip(axes, SERIES):
        ax.plot(df.index, df[col], linewidth=0.4)
        ax.set_ylabel(col, fontsize=8)
        ax.tick_params(labelsize=7)
    fig.suptitle("Full series overview")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "01_full_series_overview.png", dpi=110)
    plt.close(fig)


def plot_sample_week(df: pd.DataFrame) -> None:
    week = df.loc["2019-06-03":"2019-06-10"]
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(week.index, week["solar_mw"], label="solar")
    axes[0].plot(week.index, week["wind_mw"], label="wind")
    axes[0].legend(); axes[0].set_title("Generation, sample week")
    axes[1].plot(week.index, week["load_mw"], label="load actual")
    axes[1].plot(week.index, week["load_forecast_tso_mw"], label="TSO forecast", alpha=0.7)
    axes[1].legend(); axes[1].set_title("Load, sample week")
    axes[2].plot(week.index, week["price_eur_mwh"])
    axes[2].set_title("Day-ahead price, sample week")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "02_sample_week.png", dpi=110)
    plt.close(fig)


def report(df: pd.DataFrame) -> str:
    lines = []
    lines.append(f"Rows: {len(df):,}  Range: {df.index.min()} -> {df.index.max()}")

    full_range = pd.date_range(df.index.min(), df.index.max(), freq="h")
    missing_ts = full_range.difference(df.index)
    lines.append(f"Missing hourly timestamps vs. a continuous range: {len(missing_ts)}")

    diffs = df.index.to_series().diff().dropna()
    non_hourly = diffs[diffs != pd.Timedelta(hours=1)]
    lines.append(f"Non-1h gaps between consecutive rows (possible DST/dropout): {len(non_hourly)}")
    if len(non_hourly):
        lines.append(f"  examples: {list(non_hourly.index[:5])}")

    lines.append("\nNaN counts per column:")
    for col in SERIES + ["solar_capacity_mw", "wind_capacity_mw"]:
        n = df[col].isna().sum()
        lines.append(f"  {col}: {n} ({n/len(df):.1%})")

    lines.append("\nZero-run check (consecutive-zero streaks > 6h) in solar/wind/load:")
    for col in ["solar_mw", "wind_mw", "load_mw"]:
        is_zero = df[col] == 0
        streak = is_zero.groupby((~is_zero).cumsum()).cumsum()
        max_streak = streak.max()
        lines.append(f"  {col}: longest zero-run = {max_streak}h")

    lines.append("\nImplausible negative values:")
    for col in ["solar_mw", "wind_mw", "load_mw"]:
        n_neg = (df[col] < 0).sum()
        lines.append(f"  {col}: {n_neg} negative rows")

    return "\n".join(lines)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(MERGED_PATH)
    plot_full_series(df)
    plot_sample_week(df)
    text = report(df)
    print(text)


if __name__ == "__main__":
    main()
