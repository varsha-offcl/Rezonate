"""Per-day day-ahead forecast cache for the ablation (project plan Phase 7).

The ablation's forecast-dependent rows (GA→PSO on TFT vs LSTM vs persistence)
need each model's 24h day-ahead forecast for many test days, not just the 5
the dashboard displays. Producing those means one predict pass of each trained
model over the whole test set, then tiling calendar-day-aligned 24h blocks.
This is cached to results/season_forecasts.json so the ablation itself stays
pure-CPU and fast (no model reloads per config).

Persistence isn't cached here -- it's just "yesterday's actual" (lag 24) and
the ablation derives it directly from the data.

Run:
  .venv/Scripts/python -m src.eval.season_forecast
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.forecasting.tft import (
    HORIZON,
    MODELS_DIR,
    TARGETS,
    build_frame,
    evaluate,
    make_datasets,
)

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def _load(kind: str):
    from pytorch_forecasting import RecurrentNetwork, TemporalFusionTransformer

    ckpt = MODELS_DIR / f"{kind}.ckpt"
    if not ckpt.exists():
        raise FileNotFoundError(f"{ckpt} not found -- train the models first (src.forecasting.tft)")
    cls = TemporalFusionTransformer if kind == "tft" else RecurrentNetwork
    return cls.load_from_checkpoint(str(ckpt))


def _per_day_p50(df, index_df, preds):
    """{date_iso: {target: [24 hourly p50]}} for every calendar day whose full
    24h-ahead block is available, aligned to 00:00 forecast origins."""
    ts_of_idx = dict(zip(df["time_idx"], df["timestamp"]))
    first_idx = index_df["time_idx"].to_numpy()
    pos_of_idx = {int(v): i for i, v in enumerate(first_idx)}
    last_idx = int(df["time_idx"].iloc[-1])

    out = {}
    for s in first_idx:
        s = int(s)
        start_ts = pd.Timestamp(ts_of_idx[s])
        if start_ts.hour != 0 or s + HORIZON - 1 > last_idx:
            continue  # only whole calendar days with a full 24h horizon
        w = pos_of_idx[s]
        out[start_ts.date().isoformat()] = {
            t: [float(preds[t]["p50"][w, h]) for h in range(HORIZON)] for t in TARGETS
        }
    return out


def main():
    print("Loading trained TFT + LSTM and forecasting every test day (one predict pass each)...")
    df, train_cutoff, val_cutoff = build_frame()
    _, _, test = make_datasets(df, train_cutoff, val_cutoff)

    cache = {}
    for kind in ("tft", "lstm"):
        model = _load(kind)
        _, index_df, preds = evaluate(model, test, kind)
        cache[kind] = _per_day_p50(df, index_df, preds)
        print(f"  {kind}: {len(cache[kind])} calendar days forecast")

    # keep only days both models cover, so every ablation day is comparable
    common = sorted(set(cache["tft"]) & set(cache["lstm"]))
    out = {"days": common,
           "tft": {d: cache["tft"][d] for d in common},
           "lstm": {d: cache["lstm"][d] for d in common}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "season_forecasts.json").write_text(json.dumps(out))
    print(f"Wrote {RESULTS / 'season_forecasts.json'} ({len(common)} days "
          f"{common[0]} -> {common[-1]})")


if __name__ == "__main__":
    main()
