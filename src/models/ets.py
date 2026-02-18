# ------------------------
# src\models\ets.py 
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, cast

import numpy as np
import pandas as pd

from src.utils import compat as cap

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"
DEFAULT_COVERAGE = 0.90
_Z90 = 1.645  # ~90% CI under normal approx


def _discover_fh() -> int:
    """Prefer Constants.FH if available (compat layer), else fallback to DEFAULT_FH."""
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _get_target_col() -> str:
    """Prefer Constants.TARGET_COL if available, else Close."""
    try:
        import Constants as C  # type: ignore

        return str(getattr(C, "TARGET_COL", DEFAULT_TARGET_COL))
    except Exception:
        return DEFAULT_TARGET_COL


def _ensure_bday_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("ETS requires a DatetimeIndex.")
    out = df.copy()
    out = cast(pd.DataFrame, out.sort_index())
    out = cast(pd.DataFrame, out.asfreq("B").ffill())
    return out


def _future_bdays(last_date: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return pd.date_range(
        start=pd.Timestamp(last_date) + pd.tseries.frequencies.to_offset("B"),
        periods=int(fh),
        freq="B",
    )


@dataclass(frozen=True)
class ETSResult:
    pred_df: pd.DataFrame
    model_used: str
    cols_used: List[str]


def predict_ets(
    df: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    coverage: float = DEFAULT_COVERAGE,
    trend: str = "add",
    damped_trend: bool = True,
    seasonal: Optional[str] = None,
    seasonal_periods: Optional[int] = None,
    initialization_method: str = "estimated",
) -> Optional[ETSResult]:
    """
    ETS / Holt-Winters forecast (statsmodels ExponentialSmoothing) on target series.

    Output
    ------
    ETSResult | None
      pred_df columns: ETS_Pred, ETS_Lower, ETS_Upper
      index: future business dates
    """
    if df is None or df.empty:
        return None

    if not cap.HAS_STATSMODELS:
        log.warning("ETS disabled: statsmodels is not available.")
        return None

    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore
    except Exception as e:
        log.warning("ETS disabled: could not import ExponentialSmoothing: %s", e)
        return None

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    tgt = str(target_col) if target_col else _get_target_col()
    if tgt not in df.columns:
        log.warning("ETS: target column '%s' not found. cols=%s", tgt, list(df.columns))
        return None

    df_b = _ensure_bday_index(df)
    y_num = pd.to_numeric(df_b[tgt], errors="coerce")
    y = cast(pd.Series, y_num).dropna()

    if y.empty or len(y) < 30:
        log.warning("ETS: insufficient target history after cleaning (n=%d) for %s.", len(y), ticker)
        return None

    last_date = cast(pd.Timestamp, pd.Timestamp(y.index.max()))
    future_index = _future_bdays(last_date, fh_i)

    # Fit model
    try:
        # seasonal_periods must be set when seasonal is not None in statsmodels
        if seasonal is not None and (seasonal_periods is None or int(seasonal_periods) <= 1):
            # For daily business data, no safe default; disable seasonal rather than guessing.
            log.warning(
                "ETS: seasonal='%s' requested but seasonal_periods not provided/invalid. Disabling seasonal.",
                seasonal,
            )
            seasonal = None
            seasonal_periods = None

        mod = ExponentialSmoothing(
            y.astype(float),
            trend=trend,
            damped_trend=bool(damped_trend),
            seasonal=seasonal,
            seasonal_periods=seasonal_periods,
            initialization_method=initialization_method,
        )
        res = mod.fit(optimized=True)
    except Exception as e:
        log.warning("ETS: model fit failed for %s: %s", ticker, e, exc_info=True)
        return None

    # Forecast
    try:
        mean_fc = cast(pd.Series, res.forecast(steps=fh_i))
        mean_fc.index = future_index

        # Interval: statsmodels Holt-Winters does not consistently expose prediction intervals.
        # Use residual-based normal approximation as a stable fallback.
        resid = cast(pd.Series, res.resid)
        resid = resid.replace([np.inf, -np.inf], np.nan).dropna()

        sigma = float(np.std(resid.to_numpy(dtype=float), ddof=1)) if len(resid) > 2 else 0.0
        if not np.isfinite(sigma) or sigma <= 0.0:
            sigma = float(np.std(y.to_numpy(dtype=float), ddof=1) * 0.05)

        # Coverage -> z (use 90% as default; if coverage differs, approximate via normal quantile if possible)
        z = _Z90
        cov = float(coverage)
        if 0.5 < cov < 0.999:
            # Attempt scipy if available; else keep z=1.645
            try:

                # Approx inverse CDF for standard normal via erf^-1 using a rational approximation fallback
                # We avoid requiring scipy; this is a light approximation for z.
                # Convert two-sided coverage to one-sided tail:
                p = 0.5 + cov / 2.0

                # Peter J. Acklam approximation (compact implementation)
                a = [
                    -3.969683028665376e01,
                    2.209460984245205e02,
                    -2.759285104469687e02,
                    1.383577518672690e02,
                    -3.066479806614716e01,
                    2.506628277459239e00,
                ]
                b = [
                    -5.447609879822406e01,
                    1.615858368580409e02,
                    -1.556989798598866e02,
                    6.680131188771972e01,
                    -1.328068155288572e01,
                ]
                c = [
                    -7.784894002430293e-03,
                    -3.223964580411365e-01,
                    -2.400758277161838e00,
                    -2.549732539343734e00,
                    4.374664141464968e00,
                    2.938163982698783e00,
                ]
                d = [
                    7.784695709041462e-03,
                    3.224671290700398e-01,
                    2.445134137142996e00,
                    3.754408661907416e00,
                ]

                plow = 0.02425
                phigh = 1 - plow
                if p < plow:
                    q = np.sqrt(-2 * np.log(p))
                    z = (
                        (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
                        / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
                    )
                elif p > phigh:
                    q = np.sqrt(-2 * np.log(1 - p))
                    z = -(
                        (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
                        / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
                    )
                else:
                    q = p - 0.5
                    r = q * q
                    z = (
                        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
                        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
                    )

                z = float(abs(z))
                if not np.isfinite(z) or z <= 0.0:
                    z = _Z90
            except Exception:
                z = _Z90

        lower = mean_fc - z * sigma
        upper = mean_fc + z * sigma

        out_df = pd.DataFrame(
            {
                "ETS_Pred": pd.to_numeric(mean_fc, errors="coerce"),
                "ETS_Lower": pd.to_numeric(lower, errors="coerce"),
                "ETS_Upper": pd.to_numeric(upper, errors="coerce"),
            },
            index=future_index,
        )

        cols_used = ["ETS_Pred", "ETS_Lower", "ETS_Upper"]
        return ETSResult(pred_df=out_df, model_used="ETS", cols_used=cols_used)

    except Exception as e:
        log.warning("ETS: forecast failed for %s: %s", ticker, e, exc_info=True)
        return None


# ----------------------------------------------------------------------
# Legacy-friendly adapter
# ----------------------------------------------------------------------

def predict_exp_smoothing(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Compatibility facade to match legacy call sites expecting:
        ets_df = Models.predict_exp_smoothing(df)

    Returns:
      DataFrame with ETS_Pred/ETS_Lower/ETS_Upper or None
    """
    r = predict_ets(df)
    return None if r is None else r.pred_df


__all__ = ["ETSResult", "predict_ets", "predict_exp_smoothing"]
