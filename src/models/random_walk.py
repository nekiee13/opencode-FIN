# ------------------------
# src/models/random_walk.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, cast

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"


# ----------------------------------------------------------------------
# Result structure (optional facade-friendly provenance)
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class RandomWalkResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "RW_Pred"
    lower_col: str = "RW_Lower"
    upper_col: str = "RW_Upper"
    meta: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Constants discovery (optional; compat/Constants.py may exist)
# ----------------------------------------------------------------------

def _discover_fh() -> int:
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _discover_flag(name: str, default: bool) -> bool:
    try:
        import Constants as C  # type: ignore

        return bool(getattr(C, name, default))
    except Exception:
        return default


def _discover_num(name: str, default: Any) -> Any:
    try:
        import Constants as C  # type: ignore

        return getattr(C, name, default)
    except Exception:
        return default


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a clean DatetimeIndex and stable ordering, without side effects on caller.

    Pylance note
    ------------
    Pandas stubs sometimes widen boolean indexing results to DataFrame|Series.
    Explicit .loc[row_mask, :] plus cast() forces DataFrame for the type checker.
    """
    out = df.copy()

    if not isinstance(out.index, pd.DatetimeIndex):
        try:
            out.index = pd.to_datetime(out.index, errors="coerce")
        except Exception as e:
            raise ValueError(f"RandomWalk: cannot coerce index to DatetimeIndex: {e}") from e

    mask_notna = ~out.index.isna()
    out = cast(pd.DataFrame, out.loc[mask_notna, :].copy())
    if out.empty:
        raise ValueError("RandomWalk: empty after DatetimeIndex coercion.")

    if not out.index.is_monotonic_increasing:
        out = cast(pd.DataFrame, out.sort_index())

    # Deduplicate (keep last) to match loader behavior
    if out.index.duplicated().any():
        mask_keep = ~out.index.duplicated(keep="last")
        out = cast(pd.DataFrame, out.loc[mask_keep, :].copy())

    return out


def _as_bday_series(s: pd.Series) -> pd.Series:
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ValueError("RandomWalk: series must have a DatetimeIndex.")
    s2 = cast(pd.Series, s.sort_index())
    return cast(pd.Series, s2.asfreq("B").ffill())


def _estimate_step_sigma(y: np.ndarray) -> float:
    """
    Estimate 1-step innovation scale from historical differences (robust-ish).
    Falls back to a small value if degenerate.
    """
    if y.size < 3:
        return 1e-6

    dy = np.diff(y.astype(float))
    dy = dy[np.isfinite(dy)]
    if dy.size < 2:
        return 1e-6

    s = float(np.std(dy, ddof=1))
    if np.isfinite(s) and s > 0.0:
        return s

    # MAD fallback
    med = float(np.median(dy))
    mad = float(np.median(np.abs(dy - med)))
    s2 = float(1.4826 * mad)
    if np.isfinite(s2) and s2 > 0.0:
        return s2

    return 1e-6


def _future_bday_index(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return cast(pd.DatetimeIndex, pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"))


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def predict_random_walk(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: str = DEFAULT_TARGET_COL,
    fh: Optional[int] = None,
    with_intervals: Optional[bool] = None,
    coverage: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """
    Random Walk forecaster (Close-only by default).

    Model
    -----
    - Point forecast: y_{t+h} = y_t (flat RW, drift=0)
    - Intervals: Normal approximation using sigma(diff) and sqrt(h) scaling

    Output
    ------
    DataFrame with index = future business dates and columns:
      - RW_Pred
      - RW_Lower
      - RW_Upper
    """
    if not _discover_flag("RW_ENABLED", True):
        return None

    if enriched_data is None or enriched_data.empty:
        return None

    df = _ensure_datetime_index(enriched_data)

    if target_col not in df.columns:
        if "Close" in df.columns:
            target_col = "Close"
        else:
            log.warning("RandomWalk: target column '%s' not found for %s.", target_col, ticker or "<ticker>")
            return None

    y_num = pd.to_numeric(df[target_col], errors="coerce")
    y_series = cast(pd.Series, y_num).dropna()
    if y_series.empty:
        return None

    y_series = _as_bday_series(y_series)

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    last_val = float(y_series.iloc[-1])
    if not np.isfinite(last_val):
        return None

    if with_intervals is None:
        with_intervals = bool(_discover_flag("RW_WITH_INTERVALS", True))

    cov = float(coverage) if coverage is not None else float(_discover_num("RW_COVERAGE", 0.90))
    cov = min(max(cov, 0.50), 0.99)

    z_map = {
        0.80: 1.2816,
        0.90: 1.6449,
        0.95: 1.9600,
        0.975: 2.2414,
        0.99: 2.5758,
    }
    z = z_map.get(round(cov, 3))
    if z is None:
        try:
            from scipy.stats import norm  # type: ignore

            z = float(norm.ppf((1.0 + cov) / 2.0))
        except Exception:
            z = 1.6449

    y_vals = y_series.to_numpy(dtype=float)
    sigma_1 = _estimate_step_sigma(y_vals)

    preds = np.full(shape=(int(fh_i),), fill_value=float(last_val), dtype=float)

    if bool(with_intervals):
        hs = np.arange(1, int(fh_i) + 1, dtype=float)
        sig_h = np.sqrt(hs) * float(sigma_1)
        lowers = preds - float(z) * sig_h
        uppers = preds + float(z) * sig_h
    else:
        lowers = np.full(shape=(int(fh_i),), fill_value=np.nan, dtype=float)
        uppers = np.full(shape=(int(fh_i),), fill_value=np.nan, dtype=float)

    # Avoid pd.Timestamp(Index[Any]) patterns: use scalar-like .max()
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, y_series.index.max())))
    future_dates = _future_bday_index(last_dt, int(fh_i))

    return pd.DataFrame(
        {"RW_Pred": preds.tolist(), "RW_Lower": lowers.tolist(), "RW_Upper": uppers.tolist()},
        index=future_dates,
    )


def predict_random_walk_result(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: str = DEFAULT_TARGET_COL,
    fh: Optional[int] = None,
    with_intervals: Optional[bool] = None,
    coverage: Optional[float] = None,
) -> Optional[RandomWalkResult]:
    """
    Convenience wrapper returning provenance alongside the prediction DataFrame.
    """
    df = predict_random_walk(
        enriched_data,
        ticker=ticker,
        target_col=target_col,
        fh=fh,
        with_intervals=with_intervals,
        coverage=coverage,
    )
    if df is None or df.empty:
        return None

    meta: Dict[str, Any] = {
        "ticker": ticker,
        "target_col": target_col,
        "fh": int(fh) if fh is not None else _discover_fh(),
        "with_intervals": bool(with_intervals)
        if with_intervals is not None
        else bool(_discover_flag("RW_WITH_INTERVALS", True)),
        "coverage": float(coverage) if coverage is not None else float(_discover_num("RW_COVERAGE", 0.90)),
    }

    return RandomWalkResult(
        model_used="RandomWalk",
        cols_used=(target_col,),
        pred_df=df,
        meta=meta,
    )


__all__ = ["RandomWalkResult", "predict_random_walk", "predict_random_walk_result"]
