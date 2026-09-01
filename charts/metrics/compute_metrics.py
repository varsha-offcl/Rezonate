"""
Standalone extended forecast-accuracy metrics — beyond the project's existing
RMSE / MAE / nRMSE (`src/forecasting/metrics.py`, reported in
`results/phase2_metrics.json`).

Lives entirely under `charts/metrics/`; does not modify `src/`, `frontend/`,
or any existing `results/*.json`. It only *reads* the already-trained
checkpoints (`results/models/{tft,lstm}.ckpt`) and re-runs the same test-set
evaluation pipeline the project already uses (`src.forecasting.tft.evaluate`,
the exact function that produced the official RMSE/MAE/nRMSE numbers) purely
for inference -- no retraining, no changes to any model.

Additional metrics computed here:
  Point-forecast (TFT-p50 and LSTM, both targets):
    - MAPE   (mean absolute percentage error; unreliable for solar_mw, which
              has many near-zero actuals at night -- flagged, not silently
              hidden)
    - sMAPE  (symmetric MAPE, bounded 0-200%, robust to near-zero actuals)
    - MBE    (mean bias error -- systematic over/under-prediction)
    - R^2    (coefficient of determination)
    - Pearson r
    - MASE   (seasonal, m=24h -- scaled against a same-hour-yesterday naive
              forecast, standard practice for hourly/daily-seasonal data)
  Probabilistic (TFT only, it's the only model with quantile bands):
    - PICP   (80% prediction-interval coverage: fraction of actuals falling
              inside [P10, P90], should be close to 80% if well-calibrated)
    - Sharpness (mean P90-P10 interval width -- smaller is better, but only
              meaningful alongside a good PICP)
    - Pinball / quantile loss at P10/P50/P90

Run (from repo root, venv already set up):
    .venv/Scripts/python charts/metrics/compute_metrics.py
"""

from __future__ import annotations

import csv
import json
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

MASE_LAG = 24  # seasonal naive lag, hours (daily seasonality)
NEAR_ZERO = {"solar_mw": 50.0, "wind_mw": 200.0, "load_mw": 500.0}  # MW; MAPE excludes |y_true| below this


# --------------------------------------------------------------------------- #
# Metric formulas
# --------------------------------------------------------------------------- #

def mape(y_true: np.ndarray, y_pred: np.ndarray, floor: float) -> tuple[float, float]:
    """Returns (MAPE %, fraction of points excluded for being near-zero)."""
    mask = np.abs(y_true) >= floor
    if mask.sum() == 0:
        return float("nan"), 1.0
    err = np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])
    return float(np.mean(err) * 100), float(1 - mask.mean())


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.abs(y_true) + np.abs(y_pred)
    safe = denom > 1e-9
    out = np.zeros_like(denom)
    out[safe] = 2 * np.abs(y_pred[safe] - y_true[safe]) / denom[safe]
    return float(np.mean(out) * 100)


def mbe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(y_pred - y_true))


def r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot else float("nan")


def pearson_r(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if np.std(y_true) == 0 or np.std(y_pred) == 0:
        return float("nan")
    return float(np.corrcoef(y_true, y_pred)[0, 1])


def mase(y_true: np.ndarray, y_pred: np.ndarray, naive_scale: float) -> float:
    if not naive_scale:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)) / naive_scale)


def pinball_loss(y_true: np.ndarray, y_pred_q: np.ndarray, q: float) -> float:
    diff = y_true - y_pred_q
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def picp(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y_true >= lo) & (y_true <= hi)) * 100)


def sharpness(lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean(hi - lo))


def naive_scale(actual_series: np.ndarray, lag: int) -> float:
    if len(actual_series) <= lag:
        return float("nan")
    return float(np.mean(np.abs(actual_series[lag:] - actual_series[:-lag])))


# --------------------------------------------------------------------------- #
# Load models + run the project's own evaluation pipeline (inference only)
# --------------------------------------------------------------------------- #

def load_models_and_predict():
    from src.forecasting.tft import (
        MODELS_DIR,
        TARGETS,
        build_frame,
        evaluate,
        make_datasets,
    )

    tft_ckpt = MODELS_DIR / "tft.ckpt"
    lstm_ckpt = MODELS_DIR / "lstm.ckpt"
    if not tft_ckpt.exists() or not lstm_ckpt.exists():
        raise FileNotFoundError(
            f"Expected trained checkpoints at {tft_ckpt} and {lstm_ckpt}. "
            "Train Phase 2 first (src.forecasting.tft --model both)."
        )

    print("Building test split and dataset (same as phase2_metrics.json)...")
    df, train_cutoff, val_cutoff = build_frame()
    _, _, test_ds = make_datasets(df, train_cutoff, val_cutoff)

    print("Loading TFT checkpoint and running inference on the test set...")
    from pytorch_forecasting import RecurrentNetwork, TemporalFusionTransformer

    tft_model = TemporalFusionTransformer.load_from_checkpoint(str(tft_ckpt))
    tft_metrics, _, tft_preds = evaluate(tft_model, test_ds, "tft")

    print("Loading LSTM checkpoint and running inference on the test set...")
    lstm_model = RecurrentNetwork.load_from_checkpoint(str(lstm_ckpt))
    lstm_metrics, _, lstm_preds = evaluate(lstm_model, test_ds, "lstm")

    # actuals: re-derive the same (n_windows, HORIZON, n_targets) array evaluate() used
    from src.forecasting.tft import _actuals_by_index

    actuals = _actuals_by_index(test_ds)  # (n_windows, HORIZON, n_targets)

    test_actual_series = {
        t: df.loc[df.time_idx > val_cutoff, t].to_numpy() for t in TARGETS
    }

    return TARGETS, actuals, tft_preds, lstm_preds, tft_metrics, lstm_metrics, test_actual_series


def main():
    TARGETS, actuals, tft_preds, lstm_preds, tft_metrics, lstm_metrics, test_actual_series = (
        load_models_and_predict()
    )

    results = {"tft": {}, "lstm": {}}
    rows_for_csv = []

    for t_idx, target in enumerate(TARGETS):
        y_true = actuals[:, :, t_idx].reshape(-1)
        scale = naive_scale(test_actual_series[target], MASE_LAG)
        floor = NEAR_ZERO[target]

        for model_name, preds in (("tft", tft_preds), ("lstm", lstm_preds)):
            y_pred = preds[target]["p50"].reshape(-1)
            mape_val, mape_excl = mape(y_true, y_pred, floor)
            entry = {
                "mape_pct": round(mape_val, 2) if not np.isnan(mape_val) else None,
                "mape_excluded_frac_near_zero": round(mape_excl, 3),
                "smape_pct": round(smape(y_true, y_pred), 2),
                "mbe": round(mbe(y_true, y_pred), 2),
                "r2": round(r_squared(y_true, y_pred), 4),
                "pearson_r": round(pearson_r(y_true, y_pred), 4),
                "mase_seasonal_24h": round(mase(y_true, y_pred, scale), 4),
            }
            if model_name == "tft":
                p10 = preds[target]["p10"].reshape(-1)
                p90 = preds[target]["p90"].reshape(-1)
                entry["picp_80pct_interval"] = round(picp(y_true, p10, p90), 2)
                entry["sharpness_p90_minus_p10"] = round(sharpness(p10, p90), 2)
                entry["pinball_loss_p10"] = round(pinball_loss(y_true, p10, 0.1), 3)
                entry["pinball_loss_p50"] = round(pinball_loss(y_true, y_pred, 0.5), 3)
                entry["pinball_loss_p90"] = round(pinball_loss(y_true, p90, 0.9), 3)

            results[model_name][target] = entry
            row = {"model": model_name, "target": target, **entry}
            rows_for_csv.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics_extended.json").write_text(json.dumps(results, indent=2))

    fieldnames = sorted({k for r in rows_for_csv for k in r.keys()}, key=lambda k: (k != "model", k != "target", k))
    with open(OUT / "metrics_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_for_csv)

    print(f"Wrote {OUT / 'metrics_extended.json'}")
    print(f"Wrote {OUT / 'metrics_summary.csv'}")

    make_figures(TARGETS, results, actuals, tft_preds, lstm_preds)


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #

def make_figures(TARGETS, results, actuals, tft_preds, lstm_preds):
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3, "font.size": 10})
    x = np.arange(len(TARGETS))
    width = 0.35

    def grouped_bar(metric_key, title, ylabel, filename, models=("tft", "lstm")):
        fig, ax = plt.subplots(figsize=(8, 5))
        for i, m in enumerate(models):
            vals = [results[m][t].get(metric_key) for t in TARGETS]
            vals = [v if v is not None else 0 for v in vals]
            offset = (i - (len(models) - 1) / 2) * width
            ax.bar(x + offset, vals, width, label=m.upper())
        ax.set_xticks(x)
        ax.set_xticklabels(TARGETS)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG / filename)
        plt.close(fig)

    grouped_bar("smape_pct", "sMAPE by target (lower is better)", "sMAPE (%)", "01_smape.png")
    grouped_bar("mbe", "Mean Bias Error by target (0 = unbiased)", "MBE (MW)", "02_mbe.png")
    grouped_bar("r2", "R^2 by target (closer to 1 is better)", "R^2", "03_r2.png")
    grouped_bar("mase_seasonal_24h", "MASE (seasonal, 24h) by target — below 1.0 beats the naive forecast",
                "MASE", "04_mase.png")

    # MAPE only where meaningful (load_mw always; solar/wind flagged separately)
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, m in enumerate(("tft", "lstm")):
        vals = [results[m][t]["mape_pct"] or 0 for t in TARGETS]
        offset = (i - 0.5) * width
        ax.bar(x + offset, vals, width, label=m.upper())
    excl = [results["tft"][t]["mape_excluded_frac_near_zero"] for t in TARGETS]
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n({e*100:.0f}% excluded)" for t, e in zip(TARGETS, excl)])
    ax.set_ylabel("MAPE (%)")
    ax.set_title("MAPE by target (near-zero actuals excluded — see labels)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "05_mape.png")
    plt.close(fig)

    # PICP / sharpness (TFT only)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    picp_vals = [results["tft"][t]["picp_80pct_interval"] for t in TARGETS]
    axes[0].bar(TARGETS, picp_vals, color="steelblue")
    axes[0].axhline(80, color="red", linestyle="--", label="nominal 80%")
    axes[0].set_ylabel("PICP (%)")
    axes[0].set_title("TFT 80% interval coverage (P10-P90)")
    axes[0].legend()

    sharp_vals = [results["tft"][t]["sharpness_p90_minus_p10"] for t in TARGETS]
    axes[1].bar(TARGETS, sharp_vals, color="darkorange")
    axes[1].set_ylabel("Mean P90-P10 width (MW)")
    axes[1].set_title("TFT interval sharpness (narrower = more informative)")
    fig.tight_layout()
    fig.savefig(FIG / "06_picp_sharpness.png")
    plt.close(fig)

    # Pinball loss (TFT only)
    fig, ax = plt.subplots(figsize=(8, 5))
    quantiles = ["pinball_loss_p10", "pinball_loss_p50", "pinball_loss_p90"]
    xq = np.arange(len(quantiles))
    for i, t in enumerate(TARGETS):
        vals = [results["tft"][t][q] for q in quantiles]
        ax.bar(xq + i * 0.25, vals, 0.25, label=t)
    ax.set_xticks(xq + 0.25)
    ax.set_xticklabels(["P10", "P50", "P90"])
    ax.set_ylabel("Pinball loss")
    ax.set_title("TFT pinball (quantile) loss by quantile and target")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "07_pinball_loss.png")
    plt.close(fig)

    # Predicted vs actual scatter, TFT vs LSTM, all targets
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for row, (name, preds) in enumerate((("TFT", tft_preds), ("LSTM", lstm_preds))):
        for col, t in enumerate(TARGETS):
            ax = axes[row, col]
            y_true = actuals[:, :, col].reshape(-1)
            y_pred = preds[t]["p50"].reshape(-1)
            sample = np.random.default_rng(42).choice(len(y_true), size=min(3000, len(y_true)), replace=False)
            ax.scatter(y_true[sample], y_pred[sample], s=3, alpha=0.25)
            lims = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
            ax.plot(lims, lims, color="red", linewidth=1, linestyle="--")
            ax.set_title(f"{name} — {t}")
            ax.set_xlabel("Actual (MW)")
            ax.set_ylabel("Predicted (MW)")
    fig.suptitle("Predicted vs. actual, full test set (red = perfect prediction)")
    fig.tight_layout()
    fig.savefig(FIG / "08_pred_vs_actual_scatter.png")
    plt.close(fig)

    # Residual histograms
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for row, (name, preds) in enumerate((("TFT", tft_preds), ("LSTM", lstm_preds))):
        for col, t in enumerate(TARGETS):
            ax = axes[row, col]
            y_true = actuals[:, :, col].reshape(-1)
            y_pred = preds[t]["p50"].reshape(-1)
            ax.hist(y_pred - y_true, bins=60, color="slateblue")
            ax.axvline(0, color="black", linewidth=0.8)
            ax.set_title(f"{name} — {t} residuals")
    fig.suptitle("Residual (predicted - actual) distributions, full test set")
    fig.tight_layout()
    fig.savefig(FIG / "09_residual_histograms.png")
    plt.close(fig)

    print(f"Wrote {len(list(FIG.glob('*.png')))} figures to {FIG}")


if __name__ == "__main__":
    main()
