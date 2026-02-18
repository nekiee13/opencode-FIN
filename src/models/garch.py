# ------------------------
# src/models/garch.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from src.utils import compat as cap

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"

# ----------------------------------------------------------------------
# arch_model typing helpers (kept local to avoid importing arch typing)
# ----------------------------------------------------------------------

ArchMean = Literal[
    "Constant",
    "Zero",
    "LS",
    "AR",
    "ARX",
    "HAR",
    "HARX",
    "constant",
    "zero",
]
ArchVol = Literal["GARCH", "ARCH", "EGARCH", "FIGARCH", "APARCH", "HARCH"]
ArchDist = Literal[
    "normal",
    "gaussian",
    "t",
    "studentst",
    "skewstudent",
    "skewt",
    "ged",
    "generalized error",
]


def _normalize_arch_mean(v: str) -> ArchMean:
    s = str(v).strip()
    allowed = cast(
        Tuple[ArchMean, ...],
        (
            "Constant",
            "Zero",
            "LS",
            "AR",
            "ARX",
            "HAR",
            "HARX",
            "constant",
            "zero",
        ),
    )
    return cast(ArchMean, s) if s in allowed else cast(ArchMean, "ARX")


def _normalize_arch_vol(v: str) -> ArchVol:
    s = str(v).strip()
    allowed = cast(
        Tuple[ArchVol, ...],
        ("GARCH", "ARCH", "EGARCH", "FIGARCH", "APARCH", "HARCH"),
    )
    return cast(ArchVol, s) if s in allowed else cast(ArchVol, "GARCH")


def _normalize_arch_dist(v: str) -> ArchDist:
    s = str(v).strip().lower()
    allowed = cast(
        Tuple[ArchDist, ...],
        (
            "normal",
            "gaussian",
            "t",
            "studentst",
            "skewstudent",
            "skewt",
            "ged",
            "generalized error",
        ),
    )
    return cast(ArchDist, s) if s in allowed else cast(ArchDist, "normal")


# ----------------------------------------------------------------------
# Result structure
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class GARCHResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "GARCH_Pred"
    lower_col: str = "GARCH_Lower"
    upper_col: str = "GARCH_Upper"
    meta: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Constants discovery (optional)
# ----------------------------------------------------------------------

def _discover_fh() -> int:
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _discover_target_col() -> str:
    try:
        import Constants as C  # type: ignore

        return str(getattr(C, "TARGET_COL", DEFAULT_TARGET_COL))
    except Exception:
        return DEFAULT_TARGET_COL


def _as_bday(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("GARCH model requires DatetimeIndex input.")
    out = df.copy()
    out = cast(pd.DataFrame, out.sort_index())
    out = cast(pd.DataFrame, out.asfreq("B").ffill())
    return out


def _to_2d_exog(exog: Optional[pd.DataFrame], index: pd.DatetimeIndex) -> Optional[pd.DataFrame]:
    if exog is None or exog.empty:
        return None

    ex = exog.copy()
    if not isinstance(ex.index, pd.DatetimeIndex):
        raise ValueError("exog must have a DatetimeIndex.")

    ex = cast(pd.DataFrame, ex.sort_index())
    ex = cast(pd.DataFrame, ex.reindex(index=index))

    # numeric coercion
    ex = cast(pd.DataFrame, ex.apply(pd.to_numeric, errors="coerce"))

    # drop columns entirely NaN
    ex = cast(pd.DataFrame, ex.dropna(axis=1, how="all"))
    if ex.empty:
        return None

    # forward-fill, then drop remaining NaNs row-wise (arch requires complete rows)
    ex = cast(pd.DataFrame, ex.ffill())
    ex = cast(pd.DataFrame, ex.dropna(axis=0, how="any"))
    if ex.empty:
        return None

    return ex


def _future_index(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return cast(pd.DatetimeIndex, pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"))


def _z_for_coverage(coverage: float) -> float:
    """
    Approximate z-score for common coverages (kept dependency-free).
    """
    c = float(coverage)
    if c >= 0.99:
        return 2.576
    if c >= 0.975:
        return 1.960
    if c >= 0.95:
        return 1.960
    if c >= 0.90:
        return 1.645
    if c >= 0.80:
        return 1.282
    return 1.645


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def predict_garch_arx(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    exog_train: Optional[pd.DataFrame] = None,
    exog_future: Optional[pd.DataFrame] = None,
    coverage: float = 0.90,
    min_samples: int = 120,
    return_scale: str = "log",  # "log" or "pct"
    mean_model: str = "ARX",  # arch mean keyword (normalized at call site)
    vol_model: str = "GARCH",  # arch vol keyword (normalized at call site)
    p: int = 1,
    q: int = 1,
    dist: str = "normal",  # arch dist keyword (normalized at call site)
) -> Optional[GARCHResult]:
    """
    ARX-GARCH forecaster.

    Output:
      DataFrame indexed by future business dates with columns:
        - GARCH_Pred
        - GARCH_Lower
        - GARCH_Upper

    Dependency gating:
      Requires `arch` (cap.HAS_ARCH). When missing, returns None (best-effort).
    """
    if not cap.HAS_ARCH:
        log.info("GARCH disabled: optional dependency 'arch' not available.")
        return None

    try:
        from arch import arch_model  # type: ignore
    except Exception as e:
        log.warning("GARCH disabled: could not import arch.arch_model: %s", e)
        return None

    if enriched_data is None or enriched_data.empty:
        return None

    tgt = str(target_col) if target_col else _discover_target_col()
    fh_i = int(fh) if fh is not None else _discover_fh()
    fh_i = fh_i if fh_i > 0 else DEFAULT_FH

    if tgt not in enriched_data.columns:
        log.warning("GARCH: target column '%s' missing for %s.", tgt, ticker or "<ticker>")
        return None

    df_b = _as_bday(enriched_data)
    close = cast(pd.Series, pd.to_numeric(df_b[tgt], errors="coerce")).dropna()
    if close.empty or len(close) < max(30, int(min_samples)):
        log.warning("GARCH: insufficient data length (%d) for %s.", len(close), ticker or "<ticker>")
        return None

    # Returns
    scale = return_scale.strip().lower()
    if scale == "pct":
        r = close.pct_change().dropna()
        r_scale_note = "pct"
    else:
        # Ensure .diff is called on a pandas Series (avoid ndarray typing).
        close_vals = close.to_numpy(dtype=float)
        log_vals = np.log(close_vals)
        log_series = pd.Series(log_vals, index=close.index, name="log_close")
        r = log_series.diff().dropna()
        r_scale_note = "log"

    r = cast(pd.Series, pd.to_numeric(r, errors="coerce")).dropna()
    if r.empty or len(r) < max(50, int(min_samples) - 1):
        log.warning("GARCH: insufficient return samples (%d) for %s.", len(r), ticker or "<ticker>")
        return None

    # Align exogenous for training (optional)
    ex_train = _to_2d_exog(exog_train, cast(pd.DatetimeIndex, r.index))
    if ex_train is not None:
        r = r.reindex(ex_train.index).dropna()
        if r.empty:
            log.warning("GARCH: return series empty after exog alignment for %s.", ticker or "<ticker>")
            return None

    # Forecast horizon index (always defined)
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, r.index.max())))
    fut_idx = _future_index(last_dt, fh_i)

    # Future exog (optional) for ARX mean
    ex_future: Optional[pd.DataFrame] = None
    if ex_train is not None:
        if exog_future is not None and not exog_future.empty:
            ex_future = exog_future.copy()
            if not isinstance(ex_future.index, pd.DatetimeIndex):
                ex_future.index = pd.to_datetime(ex_future.index, errors="coerce")
            ex_future = cast(pd.DataFrame, ex_future.sort_index())
            ex_future = cast(pd.DataFrame, ex_future.apply(pd.to_numeric, errors="coerce"))
            ex_future = cast(pd.DataFrame, ex_future.dropna(axis=1, how="all"))
            if ex_future.empty:
                ex_future = None
        if ex_future is None:
            last_row = cast(pd.Series, ex_train.iloc[-1])
            ex_future = pd.DataFrame([last_row.values] * int(fh_i), columns=list(ex_train.columns))
        # Force forecast index and fill forward
        ex_future = cast(pd.DataFrame, ex_future.copy())
        if not isinstance(ex_future.index, pd.DatetimeIndex) or ex_future.index.isna().any():
            ex_future.index = fut_idx[: len(ex_future)]
        ex_future = cast(pd.DataFrame, ex_future.reindex(index=fut_idx))
        ex_future = cast(pd.DataFrame, ex_future.ffill())
        if ex_future.isna().any(axis=None):
            last_row = cast(pd.Series, ex_train.iloc[-1])
            ex_future = pd.DataFrame([last_row.values] * int(fh_i), index=fut_idx, columns=list(ex_train.columns))

    # arch often benefits from scaling: returns in percent
    r_fit = r * 100.0

    mean_kw: ArchMean = _normalize_arch_mean(mean_model)
    vol_kw: ArchVol = _normalize_arch_vol(vol_model)
    dist_kw: ArchDist = _normalize_arch_dist(dist)

    # Model fit
    try:
        am = arch_model(
            r_fit,
            mean=mean_kw,
            vol=vol_kw,
            p=int(p),
            q=int(q),
            dist=dist_kw,
            x=ex_train if ex_train is not None else None,
            rescale=False,
        )
        # arch typing stubs may be partial; runtime object is stable.
        res = cast(Any, am.fit(disp="off"))
    except Exception as e:
        log.warning("GARCH: fit failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Forecast
    try:
        if ex_train is not None and ex_future is not None:
            fc = cast(Any, res.forecast(horizon=int(fh_i), x=ex_future))
        else:
            fc = cast(Any, res.forecast(horizon=int(fh_i)))
    except Exception as e:
        log.warning("GARCH: forecast failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Extract mean/variance forecasts for horizon (final row is standard arch convention)
    try:
        mean_fc = cast(pd.Series, cast(Any, fc.mean).iloc[-1])
        var_fc = cast(pd.Series, cast(Any, fc.variance).iloc[-1])
    except Exception as e:
        log.warning("GARCH: could not extract mean/variance for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Convert back from percent-scale
    mu_r = mean_fc.to_numpy(dtype=float) / 100.0
    sig_r = np.sqrt(np.maximum(var_fc.to_numpy(dtype=float), 0.0)) / 100.0

    # Build price path from last close
    last_close = float(close.iloc[-1])
    if not np.isfinite(last_close) or last_close <= 0.0:
        log.warning("GARCH: invalid last close for %s.", ticker or "<ticker>")
        return None

    z = _z_for_coverage(coverage)

    preds: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []

    p_prev = last_close
    for k in range(int(fh_i)):
        mu = float(mu_r[k]) if k < len(mu_r) else 0.0
        sig = float(sig_r[k]) if k < len(sig_r) else float("nan")
        if not np.isfinite(sig) or sig < 0.0:
            sig = 0.0

        r_lo = mu - z * sig
        r_hi = mu + z * sig

        if r_scale_note == "pct":
            p_pred = p_prev * (1.0 + mu)
            p_lo = p_prev * (1.0 + r_lo)
            p_hi = p_prev * (1.0 + r_hi)
        else:
            p_pred = p_prev * float(np.exp(mu))
            p_lo = p_prev * float(np.exp(r_lo))
            p_hi = p_prev * float(np.exp(r_hi))

        preds.append(float(p_pred))
        lowers.append(float(p_lo))
        uppers.append(float(p_hi))
        p_prev = float(p_pred)

    out_df = pd.DataFrame(
        {"GARCH_Pred": preds, "GARCH_Lower": lowers, "GARCH_Upper": uppers},
        index=fut_idx,
    )

    cols_used: list[str] = [tgt]
    if ex_train is not None:
        cols_used.extend([str(c) for c in ex_train.columns])

    meta: Dict[str, Any] = {
        "ticker": ticker,
        "target_col": tgt,
        "fh": int(fh_i),
        "return_scale": r_scale_note,
        "mean_model": str(mean_kw),
        "vol_model": str(vol_kw),
        "p": int(p),
        "q": int(q),
        "dist": str(dist_kw),
        "coverage": float(coverage),
        "n_obs": int(len(r)),
        "has_exog": bool(ex_train is not None),
    }

    return GARCHResult(
        model_used="ARX-GARCH" if ex_train is not None else "GARCH",
        cols_used=tuple(cols_used),
        pred_df=out_df,
        meta=meta,
    )


__all__ = ["GARCHResult", "predict_garch_arx"]
