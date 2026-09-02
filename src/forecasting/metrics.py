"""RMSE, MAE, nRMSE (normalised by the range of the actuals)."""

import numpy as np


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def nrmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_range = y_true.max() - y_true.min()
    if y_range == 0:
        return float("nan")
    return rmse(y_true, y_pred) / float(y_range)


def r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0:
        return float("nan")
    return 1.0 - ss_res / ss_tot


if __name__ == "__main__":
    y_true = np.array([1.0, 2.0, 3.0, 4.0])
    y_pred = np.array([1.0, 2.0, 3.0, 6.0])
    # errors: 0, 0, 0, 2 -> MAE = 0.5, RMSE = sqrt(4/4) = 1.0
    assert abs(mae(y_true, y_pred) - 0.5) < 1e-9, mae(y_true, y_pred)
    assert abs(rmse(y_true, y_pred) - 1.0) < 1e-9, rmse(y_true, y_pred)
    assert abs(nrmse(y_true, y_pred) - (1.0 / 3.0)) < 1e-9, nrmse(y_true, y_pred)
    print("metrics sanity checks passed")
