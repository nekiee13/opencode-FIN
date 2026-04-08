from __future__ import annotations

import numpy as np


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    yt = np.asarray(y_true, dtype=float).reshape(-1)
    yp = np.asarray(y_pred, dtype=float).reshape(-1)
    if yt.size == 0:
        return {
            "r2": 0.0,
            "mae": 0.0,
            "rmse": 0.0,
            "mape": 0.0,
            "directional_accuracy": 0.0,
        }

    err = yp - yt
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(np.square(err))))

    denom = np.where(np.abs(yt) > 1e-12, np.abs(yt), np.nan)
    mape_arr = np.abs(err) / denom
    mape = float(np.nanmean(mape_arr) * 100.0) if np.isfinite(mape_arr).any() else 0.0

    ss_res = float(np.sum(np.square(err)))
    ybar = float(np.mean(yt))
    ss_tot = float(np.sum(np.square(yt - ybar)))
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 1e-12 else 0.0

    directional = float(np.mean(np.sign(yt) == np.sign(yp)))

    return {
        "r2": r2,
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "directional_accuracy": directional,
    }
