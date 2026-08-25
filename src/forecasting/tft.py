"""Phase 2 — Temporal Fusion Transformer forecaster + LSTM comparison arm.

Both models are built on pytorch-forecasting's ``TimeSeriesDataSet`` so they
train on *identical* splits with an *equal tuning budget* (same encoder/decoder
lengths, same covariates, same trainer/early-stopping) — the fair comparison
the project plan (Phase 2) asks for.

Design / cleaning decisions
---------------------------
* **Task.** 168-hour lookback -> 24-hour-ahead horizon, matching the plan's
  once-daily day-ahead cadence. A single multi-target model forecasts solar,
  wind and load jointly (one TFT + one LSTM rather than six models — far
  cheaper on CPU, and a legitimate joint-forecasting formulation).
* **TFT** uses a quantile loss at the 10th/50th/90th percentiles, so it emits
  probabilistic bands. **LSTM** (``RecurrentNetwork``) is an autoregressive
  point forecaster (MAE loss); it is the deterministic comparison arm and has
  no bands, evaluated on the same RMSE/MAE/nRMSE as the Phase-1 baselines.
* **Known-future covariates:** calendar encodings (sin/cos of hour, day-of-week,
  month) + the six Open-Meteo weather variables. Using archived weather
  *actuals* as known-future inputs assumes perfect weather foresight — an
  idealisation appropriate for a research prototype and the covariate split the
  plan specifies. In deployment these would be weather *forecasts*.
* **Past (unknown) covariates:** the three targets' own history.
* **Price is excluded.** ``price_eur_mwh`` is 61% NaN before the 2018-10-01
  DE/AT/LU bidding-zone split (see data/NOTES.md); it is not a forecast target
  here, so rather than discard 61% of the training window it is deferred to the
  cost-objective phase (GA/PSO).
* The 63 residual NaNs in solar/wind (winter sensor dropouts, not covered by
  loader.py's 3-hour ffill) are linearly interpolated for the model only.

Outputs (written to results/, consumed by src/export/to_json.py):
  results/models/{tft,lstm}.ckpt      trained checkpoints
  results/phase2_forecast.json        aligned per-model day-ahead window
  results/phase2_metrics.json         test RMSE/MAE/nRMSE per model per target
  results/phase2_importance.json      TFT encoder/decoder variable importances

Run:
  .venv/Scripts/python -m src.forecasting.tft --model both --max-epochs 30
  .venv/Scripts/python -m src.forecasting.tft --fast          # quick smoke test
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from src.data.splits import load_splits
from src.forecasting.metrics import mae, nrmse, rmse

warnings.filterwarnings("ignore", category=UserWarning)  # lightning/pf are chatty

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
MODELS_DIR = RESULTS / "models"

TARGETS = ["solar_mw", "wind_mw", "load_mw"]
WEATHER = [
    "shortwave_radiation",
    "direct_radiation",
    "temperature_2m",
    "cloudcover",
    "windspeed_100m",
    "winddirection_100m",
]
CALENDAR = ["hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos"]
KNOWN_REALS = CALENDAR + WEATHER

ENCODER_LEN = 168
HORIZON = 24
QUANTILES = [0.1, 0.5, 0.9]
BATCH_SIZE = 128
HIDDEN_SIZE = 64
ATTENTION_HEADS = 4
SEED = 42

# Display window for the dashboard: the last N whole days of the test set.
DISPLAY_DAYS = 5


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #
def build_frame() -> tuple[pd.DataFrame, int, int]:
    """Return a pytorch-forecasting long frame plus the train/val decoder cutoffs.

    ``time_idx`` is an integer hour count from the start of the record; a single
    constant ``series`` group id makes this a one-series dataset.
    """
    train, val, test = load_splits()
    df = pd.concat([train, val, test]).sort_index()

    # Fill the residual target NaNs (small; interpolation is model-only).
    for col in TARGETS:
        df[col] = df[col].interpolate(limit_direction="both")

    idx = df.index
    df = df[TARGETS + WEATHER].copy()
    hour, dow, month = idx.hour, idx.dayofweek, idx.month
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    df["month_sin"] = np.sin(2 * np.pi * month / 12)
    df["month_cos"] = np.cos(2 * np.pi * month / 12)

    df["series"] = "DE"
    df["time_idx"] = np.arange(len(df), dtype=np.int64)
    df["timestamp"] = idx

    train_cutoff = int(df["time_idx"].iloc[len(train) - 1])  # last train decoder idx
    val_cutoff = int(df["time_idx"].iloc[len(train) + len(val) - 1])
    return df.reset_index(drop=True), train_cutoff, val_cutoff


def make_datasets(df: pd.DataFrame, train_cutoff: int, val_cutoff: int):
    from pytorch_forecasting import TimeSeriesDataSet
    from pytorch_forecasting.data import GroupNormalizer, MultiNormalizer

    normalizer = MultiNormalizer(
        [GroupNormalizer(groups=["series"]) for _ in TARGETS]
    )
    training = TimeSeriesDataSet(
        df[df.time_idx <= train_cutoff],
        time_idx="time_idx",
        target=TARGETS,
        group_ids=["series"],
        max_encoder_length=ENCODER_LEN,
        max_prediction_length=HORIZON,
        time_varying_known_reals=["time_idx"] + KNOWN_REALS,
        time_varying_unknown_reals=list(TARGETS),
        target_normalizer=normalizer,
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=False,
    )
    validation = TimeSeriesDataSet.from_dataset(
        training, df[df.time_idx <= val_cutoff],
        min_prediction_idx=train_cutoff + 1, stop_randomization=True,
    )
    test = TimeSeriesDataSet.from_dataset(
        training, df, min_prediction_idx=val_cutoff + 1, stop_randomization=True,
    )
    return training, validation, test


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def make_trainer(max_epochs: int):
    import lightning.pytorch as pl
    from lightning.pytorch.callbacks import EarlyStopping

    early_stop = EarlyStopping(
        monitor="val_loss", patience=5, mode="min", min_delta=1e-4
    )
    return pl.Trainer(
        max_epochs=max_epochs,
        accelerator="auto",  # uses the GPU automatically when a CUDA build of
        devices="auto",      # torch is installed; falls back to CPU otherwise.
        gradient_clip_val=0.1,
        callbacks=[early_stop],
        enable_progress_bar=True,
        enable_model_summary=False,
        logger=False,
        enable_checkpointing=False,
    )


def train_tft(training, validation, max_epochs: int):
    from pytorch_forecasting import TemporalFusionTransformer
    from pytorch_forecasting.metrics import MultiLoss, QuantileLoss

    train_dl = training.to_dataloader(train=True, batch_size=BATCH_SIZE, num_workers=0)
    val_dl = validation.to_dataloader(train=False, batch_size=BATCH_SIZE, num_workers=0)

    model = TemporalFusionTransformer.from_dataset(
        training,
        hidden_size=HIDDEN_SIZE,
        attention_head_size=ATTENTION_HEADS,
        dropout=0.1,
        hidden_continuous_size=32,
        loss=MultiLoss([QuantileLoss(quantiles=QUANTILES) for _ in TARGETS]),
        learning_rate=1e-3,
        log_interval=0,
        optimizer="adam",
        reduce_on_plateau_patience=3,
    )
    trainer = make_trainer(max_epochs)
    trainer.fit(model, train_dl, val_dl)
    return model


def train_lstm(training, validation, max_epochs: int):
    from pytorch_forecasting import RecurrentNetwork
    from pytorch_forecasting.metrics import MAE, MultiLoss

    train_dl = training.to_dataloader(train=True, batch_size=BATCH_SIZE, num_workers=0)
    val_dl = validation.to_dataloader(train=False, batch_size=BATCH_SIZE, num_workers=0)

    model = RecurrentNetwork.from_dataset(
        training,
        cell_type="LSTM",
        hidden_size=HIDDEN_SIZE,
        rnn_layers=2,
        dropout=0.1,
        loss=MultiLoss([MAE() for _ in TARGETS]),
        learning_rate=1e-3,
        log_interval=0,
        optimizer="adam",
    )
    trainer = make_trainer(max_epochs)
    trainer.fit(model, train_dl, val_dl)
    return model


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _actuals_by_index(test_ds) -> np.ndarray:
    """(n_windows, HORIZON, n_targets) array of decoder actuals, window order."""
    dl = test_ds.to_dataloader(train=False, batch_size=BATCH_SIZE, num_workers=0)
    outs = [[] for _ in TARGETS]
    for _, (y, _) in dl:
        # y is a list per target for multi-target datasets
        for t in range(len(TARGETS)):
            outs[t].append(y[t])
    stacked = [_to_np(torch.cat(o, dim=0)) for o in outs]  # each (n_windows, HORIZON)
    return np.stack(stacked, axis=-1)


def evaluate(model, test_ds, kind: str):
    """Pooled multi-horizon test metrics + P10/P50/P90 (or point) predictions.

    Returns (metrics_dict, index_df, preds) where preds is a dict target ->
    dict('p10'/'p50'/'p90' -> (n_windows, HORIZON) arrays); for the LSTM only
    'p50' is populated (point forecast).
    """
    dl = test_ds.to_dataloader(train=False, batch_size=BATCH_SIZE, num_workers=0)
    actuals = _actuals_by_index(test_ds)  # (n_windows, HORIZON, n_targets)

    if kind == "tft":
        raw = model.predict(dl, mode="quantiles", return_index=True)
        # raw.output: list per target of (n_windows, HORIZON, n_quantiles)
        q_by_target = raw.output
        index_df = raw.index
    else:
        raw = model.predict(dl, mode="prediction", return_index=True)
        q_by_target = raw.output  # list per target of (n_windows, HORIZON)
        index_df = raw.index

    metrics, preds = {}, {}
    for t, target in enumerate(TARGETS):
        y_true = actuals[:, :, t].reshape(-1)
        if kind == "tft":
            arr = _to_np(q_by_target[t])  # (n_windows, HORIZON, 3)
            p10, p50, p90 = arr[..., 0], arr[..., 1], arr[..., 2]
        else:
            p50 = _to_np(q_by_target[t])  # (n_windows, HORIZON)
            p10 = p90 = None
        y_pred = p50.reshape(-1)
        metrics[target] = {
            "rmse": rmse(y_true, y_pred),
            "mae": mae(y_true, y_pred),
            "nrmse": nrmse(y_true, y_pred),
        }
        preds[target] = {"p10": p10, "p50": p50, "p90": p90}
    return metrics, index_df, preds


def stitch_display_window(df, index_df, preds, kind):
    """Tile non-overlapping day-ahead windows over the last DISPLAY_DAYS days.

    Returns list of {timestamp, <target>_p10/p50/p90 or <target>} rows the
    export layer merges with the Phase-1 baselines by timestamp.
    """
    ts_of_idx = dict(zip(df["time_idx"], df["timestamp"]))
    # index_df has one row per window with its first decoder time_idx.
    first_idx = index_df["time_idx"].to_numpy()

    last_idx = int(df["time_idx"].iloc[-1])
    # Day-aligned starts so 24h blocks tile without overlap, newest DISPLAY_DAYS.
    starts = [last_idx + 1 - HORIZON * k for k in range(DISPLAY_DAYS, 0, -1)]

    pos_of_start = {int(s): int(np.where(first_idx == s)[0][0])
                    for s in starts if (first_idx == s).any()}

    rows = []
    for s in starts:
        if s not in pos_of_start:
            continue
        w = pos_of_start[s]
        for h in range(HORIZON):
            tidx = s + h
            row = {"timestamp": pd.Timestamp(ts_of_idx[tidx]).isoformat()}
            for target in TARGETS:
                p = preds[target]
                # Namespace keys by model so TFT's and LSTM's medians don't
                # collide: "<model>::<target>::<stat>".
                if kind == "tft":
                    row[f"tft::{target}::p10"] = float(p["p10"][w, h])
                    row[f"tft::{target}::p50"] = float(p["p50"][w, h])
                    row[f"tft::{target}::p90"] = float(p["p90"][w, h])
                else:
                    row[f"lstm::{target}::p50"] = float(p["p50"][w, h])
            rows.append(row)
    return rows


def tft_importance(model, test_ds):
    """Encoder/decoder variable-selection importances (normalised to sum=1)."""
    dl = test_ds.to_dataloader(train=False, batch_size=BATCH_SIZE, num_workers=0)
    raw = model.predict(dl, mode="raw", return_x=True)
    interp = model.interpret_output(raw.output, reduction="sum")

    def to_named(weights, names):
        w = _to_np(weights).astype(float)
        total = w.sum() or 1.0
        pairs = sorted(zip(names, (w / total).tolist()), key=lambda p: -p[1])
        return [{"name": n, "importance": round(v, 4)} for n, v in pairs]

    return {
        "encoder": to_named(interp["encoder_variables"], model.encoder_variables),
        "decoder": to_named(interp["decoder_variables"], model.decoder_variables),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["tft", "lstm", "both"], default="both")
    ap.add_argument("--max-epochs", type=int, default=30)
    ap.add_argument("--fast", action="store_true",
                    help="tiny subset + 1 epoch to smoke-test the pipeline")
    args = ap.parse_args()

    import lightning.pytorch as pl
    pl.seed_everything(SEED, workers=True)

    df, train_cutoff, val_cutoff = build_frame()
    if args.fast:
        # Keep a small contiguous tail and re-slice it into train/val/test so
        # every dataset is non-empty and each still has room for a 168h encoder
        # + 24h horizon. Runs in seconds; only exercises the pipeline.
        n = 1800
        df = df.iloc[-n:].reset_index(drop=True)
        df["time_idx"] = np.arange(len(df), dtype=np.int64)
        train_cutoff = int(len(df) * 0.6)
        val_cutoff = int(len(df) * 0.8)
        args.max_epochs = 1

    training, validation, test = make_datasets(df, train_cutoff, val_cutoff)
    print(f"windows — train:{len(training)} val:{len(validation)} test:{len(test)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    all_metrics, all_forecast_rows, importance = {}, {}, None

    def merge_rows(rows, kind):
        for row in rows:
            key = row["timestamp"]
            all_forecast_rows.setdefault(key, {"timestamp": key})
            for k, v in row.items():
                if k != "timestamp":
                    all_forecast_rows[key][k] = v

    if args.model in ("tft", "both"):
        print("=== Training TFT ===")
        tft = train_tft(training, validation, args.max_epochs)
        tft.trainer.save_checkpoint(str(MODELS_DIR / "tft.ckpt"))
        m, idx, preds = evaluate(tft, test, "tft")
        all_metrics["tft"] = m
        merge_rows(stitch_display_window(df, idx, preds, "tft"), "tft")
        importance = tft_importance(tft, test)
        print("TFT test metrics:", json.dumps(_round(m), indent=2))

    if args.model in ("lstm", "both"):
        print("=== Training LSTM ===")
        lstm = train_lstm(training, validation, args.max_epochs)
        lstm.trainer.save_checkpoint(str(MODELS_DIR / "lstm.ckpt"))
        m, idx, preds = evaluate(lstm, test, "lstm")
        all_metrics["lstm"] = m
        merge_rows(stitch_display_window(df, idx, preds, "lstm"), "lstm")
        print("LSTM test metrics:", json.dumps(_round(m), indent=2))

    forecast_rows = [all_forecast_rows[k] for k in sorted(all_forecast_rows)]
    (RESULTS / "phase2_metrics.json").write_text(json.dumps(_round(all_metrics)))
    (RESULTS / "phase2_forecast.json").write_text(json.dumps(forecast_rows))
    if importance is not None:
        (RESULTS / "phase2_importance.json").write_text(json.dumps(importance))
    print(f"Wrote phase2_*.json to {RESULTS} "
          f"({len(forecast_rows)} forecast rows, {len(all_metrics)} models)")


def _to_np(x):
    """Tensor (possibly on GPU) or array -> host numpy array."""
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def _round(obj, nd=4):
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


if __name__ == "__main__":
    main()
