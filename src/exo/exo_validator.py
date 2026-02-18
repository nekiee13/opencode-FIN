# ------------------------
# src\exo\exo_validator.py
# ------------------------
"""
FIN exogenous scenario validator.

Location
--------
src/exo/exo_validator.py

Purpose
-------
Validate *ABS* exogenous scenario paths against recent historical dynamics to catch
obvious contradictions (range violations, impossible domains, extreme jumps/drift).

Design notes
------------
- This module is intentionally conservative: it warns only when there is enough
  history and the contradiction is material.
- It is silent (no warnings) when it cannot validate reliably (insufficient history).
- It does not mutate inputs.
- It is compatible with the dict structure produced by src.exo.exo_config.load_exo_config().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# =============================================================================
# Parameters / Constraints
# =============================================================================

@dataclass(frozen=True)
class ValidationParams:
    window: int = 60              # lookback window for recent dynamics
    jump_sigma_mult: float = 4.0  # alpha
    drift_sigma_mult: float = 2.5 # beta
    quantile_lo: float = 0.01
    quantile_hi: float = 0.99
    min_points: int = 25          # minimum history points to validate
    eps: float = 1e-12


# Conservative domain constraints (warn only when violated)
BOUNDED_0_100 = {
    "RSI (14)",
    "Stochastic %K",
    "STOCH_%D",
    "Ultimate Oscillator",
}


# =============================================================================
# Internal helpers
# =============================================================================

def _safe_std(x: np.ndarray) -> float:
    if x.size < 2:
        return 0.0
    s = float(np.nanstd(x, ddof=1))
    if np.isnan(s) or not np.isfinite(s):
        return 0.0
    return s


def _robust_scale(x: np.ndarray, eps: float) -> float:
    """
    Robust scale using MAD as fallback if std is too small.
    """
    x = x[np.isfinite(x)]
    if x.size < 2:
        return 0.0

    s = _safe_std(x)
    if s > eps:
        return s

    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return float(1.4826 * mad)  # MAD -> approx std


def _is_atr_name(reg: str) -> bool:
    return str(reg).strip().upper().startswith("ATR")


def _is_volume_name(reg: str) -> bool:
    return str(reg).strip().lower() == "volume"


# =============================================================================
# Public validators
# =============================================================================

def validate_abs_scenario_path(
    *,
    ticker: str,
    model_name: str,
    regressor: str,
    hist_series: pd.Series,
    future_values: List[Optional[float]],
    params: ValidationParams = ValidationParams(),
) -> List[str]:
    """
    Validate a single ABS scenario path.

    Parameters
    ----------
    ticker, model_name, regressor:
        Identifiers used to format warnings.
    hist_series:
        Historical regressor series aligned to the modeling index.
    future_values:
        Scenario path values (Day_1..Day_FH) interpreted as ABS levels.
    params:
        Validation thresholds.

    Returns
    -------
    List[str]
        Warning messages; empty list => no issues found / not enough history.
    """
    warnings: List[str] = []

    # Clean history
    hs_num = pd.to_numeric(hist_series, errors="coerce")
    hs = cast(pd.Series, hs_num).dropna()

    if len(hs) < params.min_points:
        return warnings

    hs = hs.iloc[-params.window:] if len(hs) > params.window else hs
    last_val = float(hs.iloc[-1])

    # Clean future values: keep finite floats only
    svals_raw = [v for v in future_values if v is not None and np.isfinite(v)]
    if not svals_raw:
        return warnings

    svals = np.asarray(svals_raw, dtype=float)

    # A) Domain constraints
    if regressor in BOUNDED_0_100:
        if np.any(svals < -1.0) or np.any(svals > 101.0):
            warnings.append(
                f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' contains values "
                f"outside expected ~[0,100] bounds: min={float(np.min(svals)):.4f}, "
                f"max={float(np.max(svals)):.4f}."
            )

    if _is_atr_name(regressor) and np.any(svals < 0.0):
        warnings.append(
            f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' contains negative values "
            f"(ATR should be >= 0): min={float(np.min(svals)):.6f}."
        )

    if _is_volume_name(regressor) and np.any(svals < 0.0):
        warnings.append(
            f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' contains negative values "
            f"(Volume should be >= 0): min={float(np.min(svals)):.6f}."
        )

    # Recent range stats
    hs_vals = hs.to_numpy(dtype=float)
    q_lo = float(np.quantile(hs_vals, params.quantile_lo))
    q_hi = float(np.quantile(hs_vals, params.quantile_hi))
    sigma_r = _safe_std(hs_vals)
    margin = max(0.5 * sigma_r, params.eps)

    # B) Range inconsistency vs recent window
    if np.any(svals < (q_lo - margin)) or np.any(svals > (q_hi + margin)):
        warnings.append(
            f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' is outside recent regime: "
            f"recent Q{int(params.quantile_lo*100)}={q_lo:.6f}, "
            f"Q{int(params.quantile_hi*100)}={q_hi:.6f}, margin={margin:.6f}, "
            f"scenario min={float(np.min(svals)):.6f}, max={float(np.max(svals)):.6f}."
        )

    # Recent daily-change scale
    d_hist = np.diff(hs_vals)
    sigma_d = _robust_scale(d_hist, params.eps)
    if sigma_d <= params.eps:
        sigma_d = 0.0

    # Scenario step diffs relative to last observed
    d_s: List[float] = [float(svals[0] - last_val)]
    if svals.size > 1:
        d_s.extend((svals[1:] - svals[:-1]).astype(float).tolist())
    d_s_arr = np.asarray(d_s, dtype=float)

    # C) Jump-size contradiction
    if sigma_d > 0.0:
        thr = params.jump_sigma_mult * sigma_d
        if np.any(np.abs(d_s_arr) > thr):
            warnings.append(
                f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' implies step changes larger than "
                f"{params.jump_sigma_mult:.1f}× recent daily-change scale: sigma(diff)≈{sigma_d:.6f}, "
                f"threshold≈{thr:.6f}, max|step|={float(np.max(np.abs(d_s_arr))):.6f}."
            )

        # D) Drift contradiction vs recent trend
        mu_hist = float(np.mean(d_hist)) if d_hist.size else 0.0
        mu_scen = float(np.mean(d_s_arr[1:])) if d_s_arr.size > 1 else float(d_s_arr[0])
        thr_mu = params.drift_sigma_mult * sigma_d
        if abs(mu_scen - mu_hist) > thr_mu:
            warnings.append(
                f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' drift deviates from recent drift: "
                f"recent mean(diff)≈{mu_hist:.6f}, scenario mean(step)≈{mu_scen:.6f}, "
                f"allowed deviation≈{thr_mu:.6f}."
            )

    # E) Indicator-specific heuristics
    if regressor == "RSI (14)":
        if np.any(np.abs(d_s_arr) > 12.0):
            warnings.append(
                f"[EXO][{ticker}][{model_name}] ABS path for 'RSI (14)' implies a large day-to-day jump "
                f"(>12 points). max|jump|={float(np.max(np.abs(d_s_arr))):.4f}."
            )

    if _is_atr_name(regressor):
        denom = max(abs(last_val), params.eps)
        rel_jump = abs(float(svals[0] - last_val)) / denom
        if rel_jump > 0.35:
            warnings.append(
                f"[EXO][{ticker}][{model_name}] ABS path for '{regressor}' implies a large one-step relative jump "
                f"(>{0.35:.2f}). last={last_val:.6f}, day1={float(svals[0]):.6f}, rel_jump={rel_jump:.3f}."
            )

    return warnings


def validate_exo_config_for_run(
    *,
    ticker: str,
    model_name: str,
    enriched_data: pd.DataFrame,
    target_index: pd.Index,
    exo_config: Dict[str, Any],
    params: ValidationParams = ValidationParams(),
) -> None:
    """
    Emit logger warnings for ABS paths that contradict recent dynamics.

    This function is intentionally silent when it lacks enough history.

    Parameters
    ----------
    ticker, model_name:
        Active run identifiers.
    enriched_data:
        Model-ready dataset with regressor columns.
    target_index:
        Index to align history to (typically the model's training index).
    exo_config:
        Config dict in the shape produced by src.exo.exo_config.load_exo_config().
    params:
        Validation thresholds.
    """
    if not exo_config:
        return

    model_cfg = exo_config.get(model_name, {})
    ticker_cfg = model_cfg.get(ticker, {})
    if not ticker_cfg:
        return

    for regressor, cfg in ticker_cfg.items():
        if not cfg or not cfg.get("enabled", False):
            continue

        scenario_mode = str(cfg.get("scenario_mode", "NONE")).upper()
        if scenario_mode != "ABS":
            continue

        if regressor not in enriched_data.columns:
            continue

        hist_series = cast(pd.Series, enriched_data[regressor]).reindex(index=target_index)
        future_values = list(cfg.get("values", []))

        msgs = validate_abs_scenario_path(
            ticker=ticker,
            model_name=model_name,
            regressor=str(regressor),
            hist_series=hist_series,
            future_values=future_values,
            params=params,
        )
        for msg in msgs:
            log.warning(msg)


__all__ = [
    "ValidationParams",
    "validate_abs_scenario_path",
    "validate_exo_config_for_run",
]
