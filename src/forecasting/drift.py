"""Concept-drift detection over the TFT's forecast error (project plan
section 11, Phase 6 -- the forecaster's "drift-triggered retraining"
mechanism).

This module currently runs in DIAGNOSE-ONLY mode: it loads the trained TFT,
forecasts the whole test season, builds a rolling forecast-error stream, and
runs a Page-Hinkley change detector (river) over it to see whether the season
actually exhibits concept drift -- WITHOUT retraining anything yet. The point
is to find out, honestly, whether the plan's hoped-for "error rises then
recovers after each retrain" figure is even applicable to this data before
spending GPU on incremental retraining. (The TFT already absorbs seasonality
through its calendar covariates, so the residual error may well be
stationary.)

Error stream: for each 24h-ahead forecast window (one per test hour), the
mean absolute error over its horizon, normalised per target by that target's
range so solar/wind/load are comparable, then averaged across the three
targets. Page-Hinkley consumes that stream in forecast-origin order.

Run:
  .venv/Scripts/python -m src.forecasting.drift
"""

from __future__ import annotations

import json
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from river import drift

from src.forecasting.tft import (
    HORIZON,
    MODELS_DIR,
    TARGETS,
    _actuals_by_index,
    build_frame,
    evaluate,
    make_datasets,
)

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def load_tft():
    from pytorch_forecasting import TemporalFusionTransformer

    ckpt = MODELS_DIR / "tft.ckpt"
    if not ckpt.exists():
        raise FileNotFoundError(f"{ckpt} not found -- train the TFT first (src.forecasting.tft)")
    return TemporalFusionTransformer.load_from_checkpoint(str(ckpt))


def error_stream():
    """Return (timestamps, err) -- per-window normalised forecast error over
    the test season, in forecast-origin order."""
    df, train_cutoff, val_cutoff = build_frame()
    _, _, test = make_datasets(df, train_cutoff, val_cutoff)
    model = load_tft()

    _, index_df, preds = evaluate(model, test, "tft")
    actuals = _actuals_by_index(test)  # (n_windows, HORIZON, n_targets)

    err = np.zeros(actuals.shape[0])
    for i, t in enumerate(TARGETS):
        rng = actuals[:, :, i].max() - actuals[:, :, i].min()
        mae_w = np.abs(preds[t]["p50"] - actuals[:, :, i]).mean(axis=1)
        err += mae_w / (rng if rng else 1.0)
    err /= len(TARGETS)

    time_idx = index_df["time_idx"].to_numpy()
    order = np.argsort(time_idx)
    err, time_idx = err[order], time_idx[order]
    ts_of_idx = dict(zip(df["time_idx"], df["timestamp"]))
    timestamps = [pd.Timestamp(ts_of_idx[ti]) for ti in time_idx]
    return timestamps, err


def detect(timestamps, err):
    ph = drift.PageHinkley()
    triggers = []
    for i, e in enumerate(err):
        ph.update(float(e))
        if ph.drift_detected:
            triggers.append(i)
    return triggers


def daily_mean(timestamps, err):
    by_day = defaultdict(list)
    for ts, e in zip(timestamps, err):
        by_day[ts.date().isoformat()].append(e)
    days = sorted(by_day)
    return days, [float(np.mean(by_day[d])) for d in days]


def main():
    print("Loading trained TFT and forecasting the full test season (no retraining)...")
    timestamps, err = error_stream()
    triggers = detect(timestamps, err)

    print(f"Test season: {timestamps[0].date()} -> {timestamps[-1].date()}  "
          f"({len(err)} forecast windows)")
    print(f"Normalised forecast error: mean {err.mean():.4f}  std {err.std():.4f}  "
          f"min {err.min():.4f}  max {err.max():.4f}")
    print(f"Page-Hinkley drift triggers: {len(triggers)}")
    for i in triggers[:20]:
        print(f"  trigger at {timestamps[i]}  (error {err[i]:.4f})")
    if len(triggers) > 20:
        print(f"  ... and {len(triggers) - 20} more")

    days, daily_err = daily_mean(timestamps, err)
    trigger_ts = [timestamps[i].isoformat() for i in triggers]
    out = {
        "days": days,
        "daily_error": [round(e, 5) for e in daily_err],
        "trigger_timestamps": trigger_ts,
        "n_windows": len(err),
        "error_mean": round(float(err.mean()), 5),
        "error_std": round(float(err.std()), 5),
        "retrained": False,  # diagnose-only run
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "drift.json").write_text(json.dumps(out))
    print(f"Wrote {RESULTS / 'drift.json'}")


if __name__ == "__main__":
    main()
