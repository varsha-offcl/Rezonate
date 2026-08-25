"""Load OPSD (DE energy) + Open-Meteo (Berlin weather), join on UTC hourly
timestamp, and save a single clean parquet to data/processed/merged.parquet.

Cleaning decisions (see data/NOTES.md for the data-quality report that
motivated them):
  - OPSD is loaded with `usecols` (150+ columns in the raw file; only the
    Germany energy columns named in the project plan are needed).
  - Open-Meteo's CSV has a 2-line location header before the real header row;
    skip it explicitly rather than relying on pandas' header-guessing.
  - Both series are UTC and hourly, so an inner join on timestamp is safe:
    it naturally restricts to the overlapping date range (Open-Meteo:
    2016-01-01 onward; OPSD: through 2020-09-30) without manual date math.
  - Remaining short gaps (sensor dropouts) are forward-filled up to 3 hours;
    anything longer is left as NaN and dropped at the feature stage, not
    silently imputed away.
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

OPSD_PATH = RAW_DIR / "opsd_time_series_60min.csv"
WEATHER_PATH = RAW_DIR / "open_meteo_weather.csv"
OUTPUT_PATH = PROCESSED_DIR / "merged.parquet"

OPSD_COLS = [
    "utc_timestamp",
    "DE_solar_generation_actual",
    "DE_wind_generation_actual",
    "DE_load_actual_entsoe_transparency",
    "DE_load_forecast_entsoe_transparency",
    "DE_LU_price_day_ahead",
    "DE_solar_capacity",
    "DE_wind_capacity",
]

RENAME = {
    "DE_solar_generation_actual": "solar_mw",
    "DE_wind_generation_actual": "wind_mw",
    "DE_load_actual_entsoe_transparency": "load_mw",
    "DE_load_forecast_entsoe_transparency": "load_forecast_tso_mw",
    "DE_LU_price_day_ahead": "price_eur_mwh",
    "DE_solar_capacity": "solar_capacity_mw",
    "DE_wind_capacity": "wind_capacity_mw",
    "shortwave_radiation (W/m²)": "shortwave_radiation",
    "direct_radiation (W/m²)": "direct_radiation",
    "temperature_2m (°C)": "temperature_2m",
    "cloudcover (%)": "cloudcover",
    "windspeed_100m (km/h)": "windspeed_100m",
    "winddirection_100m (°)": "winddirection_100m",
}


def load_opsd() -> pd.DataFrame:
    df = pd.read_csv(OPSD_PATH, usecols=OPSD_COLS, parse_dates=["utc_timestamp"])
    df = df.rename(columns={"utc_timestamp": "timestamp", **RENAME})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df = df.set_index("timestamp").sort_index()
    return df


def load_weather() -> pd.DataFrame:
    # Row 0: coordinates. Row 1: blank. Row 2: real header. Data from row 3.
    df = pd.read_csv(WEATHER_PATH, skiprows=3)
    df = df.rename(columns={"time": "timestamp", **RENAME})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df = df.set_index("timestamp").sort_index()
    return df


def build_merged() -> pd.DataFrame:
    opsd = load_opsd()
    weather = load_weather()

    merged = opsd.join(weather, how="inner")
    merged = merged[~merged.index.duplicated(keep="first")]

    full_range = pd.date_range(merged.index.min(), merged.index.max(), freq="h")
    merged = merged.reindex(full_range)
    merged.index.name = "timestamp"

    merged = merged.ffill(limit=3)

    return merged


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    merged = build_merged()
    merged.to_parquet(OUTPUT_PATH)
    print(f"Saved {len(merged):,} rows x {merged.shape[1]} cols -> {OUTPUT_PATH}")
    print(f"Range: {merged.index.min()} -> {merged.index.max()}")
    print("NaN counts:")
    print(merged.isna().sum())


if __name__ == "__main__":
    main()
