from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Optional

import numpy as np


@dataclass(frozen=True)
class PISettings:
    coverage: float
    alpha: float
    q_low: float
    q_high: float
    z_two_sided: float
    calibration_enabled: bool
    calibration_min_samples: int


def _discover(name: str, default: Any) -> Any:
    try:
        import Constants as C  # type: ignore

        return getattr(C, name, default)
    except Exception:
        return default


def discover_pi_settings() -> PISettings:
    raw_cov = float(_discover("PI_COVERAGE", 0.90))
    coverage = min(0.999, max(0.01, raw_cov))

    raw_alpha = _discover("PI_ALPHA", None)
    if raw_alpha is None:
        alpha = 1.0 - coverage
    else:
        alpha = min(0.99, max(0.001, float(raw_alpha)))
        coverage = 1.0 - alpha

    q_low = float(_discover("PI_Q_LOW", alpha / 2.0))
    q_high = float(_discover("PI_Q_HIGH", 1.0 - alpha / 2.0))

    if not (0.0 < q_low < q_high < 1.0):
        q_low = alpha / 2.0
        q_high = 1.0 - alpha / 2.0

    z = float(NormalDist().inv_cdf(1.0 - alpha / 2.0))
    calib_enabled = bool(_discover("PI_CALIBRATION_ENABLED", True))
    calib_min = max(5, int(_discover("PI_CALIBRATION_MIN_SAMPLES", 30)))

    return PISettings(
        coverage=coverage,
        alpha=alpha,
        q_low=q_low,
        q_high=q_high,
        z_two_sided=z,
        calibration_enabled=calib_enabled,
        calibration_min_samples=calib_min,
    )


def residual_quantile_expansion(
    residuals: Optional[np.ndarray],
    *,
    alpha: float,
    min_samples: int,
) -> float:
    if residuals is None:
        return 0.0

    arr = np.asarray(residuals, dtype=float).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size < int(min_samples):
        return 0.0

    q = min(0.999, max(0.50, 1.0 - float(alpha)))
    return float(np.quantile(np.abs(arr), q))


__all__ = ["PISettings", "discover_pi_settings", "residual_quantile_expansion"]
