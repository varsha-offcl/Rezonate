"""Baseline forecasters: persistence, seasonal-naive, LightGBM.

Framing: all baselines predict the value at hour t using only information
available at t-24h (i.e. a forecast "made" 24h ahead, in line with the
project's once-daily day-ahead cadence). This keeps every baseline directly
comparable on the same task without recursive multi-step forecasting, which
is left to the TFT in Phase 2 (168h lookback -> 24h horizon, trained
end-to-end). Using only lag >= 24h features guarantees no leakage across the
forecast origin.

ARIMA is skipped here (cut-first item per the project plan, section 9) to
protect the dashboard deadline.
"""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.data.splits import load_splits
from src.forecasting.metrics import mae, nrmse, rmse

TARGETS = ["solar_mw", "wind_mw", "load_mw"]
LAGS = [24, 48, 72, 168]


def add_features(df: pd.DataFrame, target: str) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["y"] = df[target]
    for lag in LAGS:
        out[f"lag_{lag}"] = df[target].shift(lag)
    out["roll_mean_lag24_3"] = df[target].shift(24).rolling(3).mean()
    hour = df.index.hour
    dow = df.index.dayofweek
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    out["month"] = df.index.month
    return out.dropna()


def run_for_target(target: str, train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame):
    full = pd.concat([train, val, test])
    feats_full = add_features(full, target)

    train_idx = feats_full.index.intersection(train.index)
    test_idx = feats_full.index.intersection(test.index)

    X_cols = [c for c in feats_full.columns if c != "y"]
    X_train, y_train = feats_full.loc[train_idx, X_cols], feats_full.loc[train_idx, "y"]
    X_test, y_test = feats_full.loc[test_idx, X_cols], feats_full.loc[test_idx, "y"]

    model = lgb.LGBMRegressor(
        n_estimators=300, learning_rate=0.05, num_leaves=31, verbosity=-1, random_state=42
    )
    model.fit(X_train, y_train)
    pred_lgb = model.predict(X_test)

    pred_persistence = feats_full.loc[test_idx, "lag_24"].to_numpy()
    pred_seasonal_naive = feats_full.loc[test_idx, "lag_168"].to_numpy()

    y_true = y_test.to_numpy()

    results = {}
    predictions = {"actual": y_true}
    for name, pred in [
        ("persistence", pred_persistence),
        ("seasonal_naive", pred_seasonal_naive),
        ("lightgbm", pred_lgb),
    ]:
        results[name] = {
            "rmse": rmse(y_true, pred),
            "mae": mae(y_true, pred),
            "nrmse": nrmse(y_true, pred),
        }
        predictions[name] = pred

    return results, predictions, test_idx, model


def main():
    train, val, test = load_splits()
    all_results = {}
    all_predictions = {}
    for target in TARGETS:
        print(f"Training baselines for {target}...")
        results, predictions, test_idx, _ = run_for_target(target, train, val, test)
        all_results[target] = results
        all_predictions[target] = (test_idx, predictions)

        print(f"  {target}:")
        for model_name, m in results.items():
            print(f"    {model_name:16s} RMSE={m['rmse']:.2f}  MAE={m['mae']:.2f}  nRMSE={m['nrmse']:.4f}")

    return all_results, all_predictions


if __name__ == "__main__":
    main()
