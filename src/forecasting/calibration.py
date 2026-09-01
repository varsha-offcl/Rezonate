"""Post-hoc interval calibration for the TFT's quantile forecasts.

`charts/metrics/compute_metrics.py` found the raw P10/P90 band under-covering
on the test season (PICP 73% solar / 45% wind / 40% load vs. a nominal 80%)
-- the quantile heads are overconfident. This applies conformalized quantile
regression (CQR, Romano et al. 2019) to fix that WITHOUT retraining:

  1. Run the already-trained TFT on the held-out *validation* split (never
     seen during training, and not the test set we report accuracy on).
  2. For each target, measure how far outside the raw [P10, P90] band the
     true value falls: score = max(P10 - y, y - P90).
  3. Take the (1 - alpha) quantile of those scores as a per-target additive
     margin, alpha = 0.2 to match the nominal 80% interval.
  4. At inference, widen the raw band by that margin: [P10 - margin, P90 +
     margin]. Under the standard conformal-prediction exchangeability
     assumption this makes the *calibrated* interval hit ~80% coverage on
     new data from the same distribution as the calibration (validation)
     set. Time-series drift between validation and test means this is an
     approximation, not a guarantee -- verified empirically below by
     checking calibrated PICP on the test set.

Nothing about the trained model changes -- this is a downstream correction
applied to the quantile outputs, stored in `results/calibration.json`.

Run:
  .venv/Scripts/python -m src.forecasting.calibration
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

CONF_LEVEL = 0.8  # matches the P10/P90 band
ALPHA = 1 - CONF_LEVEL


def _conformity_scores(y: np.ndarray, p10: np.ndarray, p90: np.ndarray) -> np.ndarray:
    """How far outside [p10, p90] the true value falls; negative = inside."""
    return np.maximum(p10 - y, y - p90)


def _margin_from_scores(scores: np.ndarray) -> float:
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * (1 - ALPHA)) / n)
    return float(np.quantile(scores, level))


def compute_margins():
    """Fit per-target calibration margins on the validation split."""
    from src.forecasting.tft import (
        MODELS_DIR,
        TARGETS,
        _actuals_by_index,
        build_frame,
        evaluate,
        make_datasets,
    )
    from pytorch_forecasting import TemporalFusionTransformer

    print("Building frame + datasets, loading TFT checkpoint...")
    df, train_cutoff, val_cutoff = build_frame()
    _, validation, test = make_datasets(df, train_cutoff, val_cutoff)
    model = TemporalFusionTransformer.load_from_checkpoint(
        str(MODELS_DIR / "tft.ckpt")
    )

    print("Running inference on the validation split (calibration set)...")
    _, _, val_preds = evaluate(model, validation, "tft")
    val_actuals = _actuals_by_index(validation)

    margins = {}
    for i, target in enumerate(TARGETS):
        y = val_actuals[:, :, i].reshape(-1)
        p10 = val_preds[target]["p10"].reshape(-1)
        p90 = val_preds[target]["p90"].reshape(-1)
        scores = _conformity_scores(y, p10, p90)
        margins[target] = {
            "margin_mw": round(_margin_from_scores(scores), 2),
            "calibration_n": int(len(scores)),
            "raw_picp_pct_on_calibration_set": round(
                float(np.mean((y >= p10) & (y <= p90)) * 100), 2
            ),
        }

    return margins, df, val_cutoff, model, test, TARGETS


def calibrate(p10: np.ndarray, p90: np.ndarray, target: str, margins: dict):
    """Apply a fitted margin to raw TFT quantile bounds for one target."""
    m = margins[target]["margin_mw"]
    return p10 - m, p90 + m


def verify_on_test(margins, model, test, TARGETS):
    """Sanity check: does the calibrated band actually hit ~80% coverage on
    the (unseen-by-calibration) test set?"""
    from src.forecasting.tft import _actuals_by_index, evaluate

    print("Running inference on the test split to verify calibration...")
    _, _, test_preds = evaluate(model, test, "tft")
    test_actuals = _actuals_by_index(test)

    report = {}
    for i, target in enumerate(TARGETS):
        y = test_actuals[:, :, i].reshape(-1)
        p10_raw = test_preds[target]["p10"].reshape(-1)
        p90_raw = test_preds[target]["p90"].reshape(-1)
        p10_cal, p90_cal = calibrate(p10_raw, p90_raw, target, margins)

        report[target] = {
            "picp_raw_pct": round(float(np.mean((y >= p10_raw) & (y <= p90_raw)) * 100), 2),
            "picp_calibrated_pct": round(float(np.mean((y >= p10_cal) & (y <= p90_cal)) * 100), 2),
            "sharpness_raw_mw": round(float(np.mean(p90_raw - p10_raw)), 2),
            "sharpness_calibrated_mw": round(float(np.mean(p90_cal - p10_cal)), 2),
        }
    return report


def main():
    margins, df, val_cutoff, model, test, TARGETS = compute_margins()
    verification = verify_on_test(margins, model, test, TARGETS)

    out = {"margins": margins, "test_set_verification": verification}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "calibration.json").write_text(json.dumps(out, indent=2))

    print("\n=== Calibration margins (fit on validation set) ===")
    for t in TARGETS:
        print(f"  {t:10s} margin=+/-{margins[t]['margin_mw']:>8.1f} MW  "
              f"(raw val PICP {margins[t]['raw_picp_pct_on_calibration_set']}%)")

    print("\n=== Test-set verification: raw vs. calibrated PICP (target 80%) ===")
    for t in TARGETS:
        r = verification[t]
        print(f"  {t:10s} raw={r['picp_raw_pct']:>6.2f}%  "
              f"calibrated={r['picp_calibrated_pct']:>6.2f}%  "
              f"(sharpness {r['sharpness_raw_mw']:.0f} -> {r['sharpness_calibrated_mw']:.0f} MW)")

    print(f"\nWrote {RESULTS / 'calibration.json'}")


if __name__ == "__main__":
    main()
