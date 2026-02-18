# ------------------------
# src/models/var.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"


# ----------------------------------------------------------------------
# Result structure (facade-friendly provenance)
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class VARResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "VAR_Pred"
    lower_col: str = "VAR_Lower"
    upper_col: str = "VAR_Upper"
    meta: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Optional Constants / dependency gating
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


def _has_statsmodels() -> bool:
    # Prefer FIN capability detection if present
    try:
        from src.utils import compat  # type: ignore

        return bool(getattr(compat, "HAS_STATSMODELS", False))
    except Exception:
        try:
            import statsmodels  # noqa: F401
        except Exception:
            return False
        return True


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure DatetimeIndex and stable ordering.

    Pylance note
    ------------
    Pandas stubs can widen boolean indexing results to DataFrame|Series.
    Explicit .loc[mask, :] plus cast() forces DataFrame for the type checker.
    """
    out = df.copy()

    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")

    mask_notna = ~out.index.isna()
    out = cast(pd.DataFrame, out.loc[mask_notna, :].copy())
    if out.empty:
        raise ValueError("VAR: empty after DatetimeIndex coercion.")

    if out.index.duplicated().any():
        mask_keep = ~out.index.duplicated(keep="last")
        out = cast(pd.DataFrame, out.loc[mask_keep, :].copy())

    if not out.index.is_monotonic_increasing:
        out = cast(pd.DataFrame, out.sort_index())

    return out


def _as_bday_df(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("VAR: DataFrame must have a DatetimeIndex.")
    out = cast(pd.DataFrame, df.sort_index())
    return cast(pd.DataFrame, out.asfreq("B").ffill())


def _z_from_coverage(cov: float) -> float:
    cov2 = float(cov)
    cov2 = min(max(cov2, 0.50), 0.99)
    z_map = {
        0.80: 1.2816,
        0.90: 1.6449,
        0.95: 1.9600,
        0.975: 2.2414,
        0.99: 2.5758,
    }
    z = z_map.get(round(cov2, 3))
    if z is not None:
        return float(z)
    try:
        from scipy.stats import norm  # type: ignore

        return float(norm.ppf((1.0 + cov2) / 2.0))
    except Exception:
        return 1.6449


def _select_columns_for_var(
    df: pd.DataFrame,
    *,
    target_col: str,
    exog_cols: Optional[Sequence[str]],
) -> Tuple[pd.DataFrame, List[str], str]:
    """
    Select endogenous columns for VAR.

    In this FIN context, extra series are treated as endogenous (standard VAR).
    """
    tgt = str(target_col)

    if tgt not in df.columns:
        if "Close" in df.columns:
            tgt = "Close"
        else:
            raise ValueError(f"VAR: target '{tgt}' not in columns={list(df.columns)}")

    cols: List[str] = [tgt]

    if exog_cols:
        for c in exog_cols:
            c2 = str(c)
            if c2 in df.columns and c2 not in cols:
                cols.append(c2)
    else:
        for c in ("Open", "High", "Low", "Close"):
            if c in df.columns and c not in cols:
                cols.append(c)

    sub = cast(pd.DataFrame, df.loc[:, cols].copy())
    for c in cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")

    sub = cast(pd.DataFrame, sub.dropna(how="any"))
    if sub.empty:
        raise ValueError("VAR: no data after numeric coercion and dropna on selected columns.")

    return sub, cols, tgt


def _future_bday_index(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return cast(pd.DatetimeIndex, pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"))


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def predict_var(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: str = DEFAULT_TARGET_COL,
    fh: Optional[int] = None,
    exog_cols: Optional[Sequence[str]] = None,
    maxlags: Optional[int] = None,
    ic: Optional[str] = None,
    trend: Optional[str] = None,
    with_intervals: Optional[bool] = None,
    coverage: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """
    VAR forecaster (statsmodels VAR) in a FIN-compatible minimal interface.

    Output
    ------
    DataFrame indexed by future business dates (B), columns:
      - VAR_Pred
      - VAR_Lower
      - VAR_Upper
    """
    if not _discover_flag("VAR_ENABLED", True):
        return None
    if enriched_data is None or enriched_data.empty:
        return None
    if not _has_statsmodels():
        log.warning("VAR: statsmodels not available; skipping VAR model.")
        return None

    try:
        from statsmodels.tsa.api import VAR  # type: ignore
    except Exception as e:
        log.warning("VAR: failed to import statsmodels VAR: %s", e)
        return None

    df = _as_bday_df(_ensure_datetime_index(enriched_data))

    fh_i = int(fh) if fh is not None else _discover_fh()
    fh_i = fh_i if fh_i > 0 else DEFAULT_FH

    maxlags_i = int(maxlags) if maxlags is not None else int(_discover_num("VAR_MAXLAGS", 10))
    maxlags_i = max(1, maxlags_i)

    ic_s = str(ic) if ic is not None else str(_discover_num("VAR_IC", "aic"))
    ic_s = ic_s.lower().strip()
    if ic_s in ("none", "", "null"):
        ic_s = "aic"

    trend_s = str(trend) if trend is not None else str(_discover_num("VAR_TREND", "c"))
    trend_s = trend_s.lower().strip()

    if with_intervals is None:
        with_intervals = bool(_discover_flag("VAR_WITH_INTERVALS", True))

    cov = float(coverage) if coverage is not None else float(_discover_num("VAR_COVERAGE", 0.90))
    z = _z_from_coverage(cov)

    try:
        sub, cols_used, tgt_used = _select_columns_for_var(df, target_col=target_col, exog_cols=exog_cols)
    except Exception as e:
        log.warning("VAR: column selection failed for %s: %s", ticker or "<ticker>", e)
        return None

    if len(sub) < max(30, 5 * len(cols_used)):
        log.warning(
            "VAR: insufficient rows (%d) for stable VAR on %d vars for %s.",
            len(sub),
            len(cols_used),
            ticker or "<ticker>",
        )
        return None

    # Fit VAR
    try:
        model = VAR(sub)
        res = model.fit(maxlags=maxlags_i, ic=ic_s, trend=trend_s)
    except Exception as e:
        log.warning("VAR: fit failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Forecast
    try:
        y0 = sub.values[-res.k_ar :]  # shape: (k_ar, k_endog)
        fc = res.forecast(y=y0, steps=int(fh_i))
        fc_arr = np.asarray(fc, dtype=float)
    except Exception as e:
        log.warning("VAR: forecast failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Target extraction
    try:
        target_idx = cols_used.index(tgt_used)
    except Exception:
        target_idx = 0

    preds = fc_arr[:, target_idx].astype(float)

    lowers = np.full(shape=(int(fh_i),), fill_value=np.nan, dtype=float)
    uppers = np.full(shape=(int(fh_i),), fill_value=np.nan, dtype=float)

    if bool(with_intervals):
        # Prefer statsmodels interval if available
        try:
            fc_mean, fc_lower, fc_upper = res.forecast_interval(y=y0, steps=int(fh_i), alpha=1.0 - float(cov))
            fc_lower_arr = np.asarray(fc_lower, dtype=float)
            fc_upper_arr = np.asarray(fc_upper, dtype=float)
            lowers = fc_lower_arr[:, target_idx].astype(float)
            uppers = fc_upper_arr[:, target_idx].astype(float)
        except Exception:
            # Fallback: residual-based sqrt(h) scaling
            try:
                resid = np.asarray(res.resid, dtype=float)  # (nobs, k_endog)
                sigma_1 = float(np.std(resid[:, target_idx], ddof=1))
                if not np.isfinite(sigma_1) or sigma_1 <= 0.0:
                    sigma_1 = float(np.std(sub.iloc[:, target_idx].to_numpy(dtype=float)) * 0.05)
                if not np.isfinite(sigma_1) or sigma_1 <= 0.0:
                    sigma_1 = 1e-6
                hs = np.arange(1, int(fh_i) + 1, dtype=float)
                sig_h = np.sqrt(hs) * sigma_1
                lowers = preds - float(z) * sig_h
                uppers = preds + float(z) * sig_h
            except Exception:
                pass

    # Pylance fix: avoid pd.Timestamp(Index[Any]) by using scalar-like .max()
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, sub.index.max())))
    future_dates = _future_bday_index(last_dt, int(fh_i))

    return pd.DataFrame(
        {"VAR_Pred": preds.tolist(), "VAR_Lower": lowers.tolist(), "VAR_Upper": uppers.tolist()},
        index=future_dates,
    )


def predict_var_result(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: str = DEFAULT_TARGET_COL,
    fh: Optional[int] = None,
    exog_cols: Optional[Sequence[str]] = None,
    maxlags: Optional[int] = None,
    ic: Optional[str] = None,
    trend: Optional[str] = None,
    with_intervals: Optional[bool] = None,
    coverage: Optional[float] = None,
) -> Optional[VARResult]:
    """
    Convenience wrapper returning provenance alongside the prediction DataFrame.
    """
    df_pred = predict_var(
        enriched_data,
        ticker=ticker,
        target_col=target_col,
        fh=fh,
        exog_cols=exog_cols,
        maxlags=maxlags,
        ic=ic,
        trend=trend,
        with_intervals=with_intervals,
        coverage=coverage,
    )
    if df_pred is None or df_pred.empty:
        return None

    # Best-effort cols_used reconstruction (no heavy work; selection only)
    cols_used: List[str]
    try:
        df0 = _as_bday_df(_ensure_datetime_index(enriched_data))
        _, cols_used, _ = _select_columns_for_var(df0, target_col=target_col, exog_cols=exog_cols)
    except Exception:
        cols_used = [target_col]

    meta: Dict[str, Any] = {
        "ticker": ticker,
        "target_col": target_col,
        "fh": int(fh) if fh is not None else _discover_fh(),
        "maxlags": int(maxlags) if maxlags is not None else int(_discover_num("VAR_MAXLAGS", 10)),
        "ic": str(ic) if ic is not None else str(_discover_num("VAR_IC", "aic")),
        "trend": str(trend) if trend is not None else str(_discover_num("VAR_TREND", "c")),
        "with_intervals": bool(with_intervals) if with_intervals is not None else bool(_discover_flag("VAR_WITH_INTERVALS", True)),
        "coverage": float(coverage) if coverage is not None else float(_discover_num("VAR_COVERAGE", 0.90)),
    }

    return VARResult(
        model_used="VAR",
        cols_used=tuple(cols_used),
        pred_df=df_pred,
        meta=meta,
    )


__all__ = ["VARResult", "predict_var", "predict_var_result"]
