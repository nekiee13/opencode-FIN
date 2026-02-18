# ------------------------
# src/models/pce_narx.py
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

# Convergence guard: increased iterations for sklearn coordinate descent.
# This is intended to eliminate ConvergenceWarning without changing the objective.
DEFAULT_LASSO_MAX_ITER = 50_000


# ----------------------------------------------------------------------
# Result structure (optional convenience for facade-level provenance)
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class PCENARXResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "PCE_Pred"
    lower_col: str = "PCE_Lower"
    upper_col: str = "PCE_Upper"
    meta: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Optional dependency import
# ----------------------------------------------------------------------

def _import_dependencies():
    """
    Import chaospy and LassoCV lazily to keep them optional.

    Returns
    -------
    (cp, cp_expansion, LassoCV) or (None, None, None)
    """
    try:
        import chaospy as cp  # type: ignore
    except Exception:
        log.info("PCE-NARX disabled: optional dependency 'chaospy' is not available.")
        return None, None, None

    try:
        from sklearn.linear_model import LassoCV  # type: ignore
    except Exception:
        log.info("PCE-NARX disabled: optional dependency 'scikit-learn' is not available.")
        return None, None, None

    try:
        from chaospy import expansion as cp_expansion  # type: ignore
    except Exception:
        cp_expansion = None

    return cp, cp_expansion, LassoCV


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
# Core helpers
# ----------------------------------------------------------------------

def _as_bday_series(s: pd.Series) -> pd.Series:
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ValueError("PCE-NARX requires a DatetimeIndex.")
    s2 = cast(pd.Series, s.sort_index())
    return cast(pd.Series, s2.asfreq("B").ffill())


def _build_narx_dataset_from_df(
    y_series: pd.Series,
    exog_df: Optional[pd.DataFrame],
    max_lag: int,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], List[str]]:
    """
    Build NARX-style regression dataset:

        y_t ~ f(y_{t-1},...,y_{t-max_lag}, exog_t)

    Returns
    -------
    X, y, cols_used
      - cols_used starts with lag features then exog columns (if any)
    """
    if exog_df is not None and not exog_df.empty:
        common_idx = y_series.index.intersection(exog_df.index)
        y_subset = y_series.loc[common_idx]
        exog_subset = exog_df.loc[common_idx]
    else:
        y_subset = y_series
        exog_subset = None

    if len(y_subset) <= int(max_lag):
        return None, None, []

    X_list: List[List[float]] = []
    y_list: List[float] = []

    vals_y = y_subset.to_numpy(dtype=float)
    vals_exog = exog_subset.to_numpy(dtype=float) if exog_subset is not None else None

    cols_used: List[str] = [f"y_lag{lag}" for lag in range(1, int(max_lag) + 1)]
    if exog_subset is not None:
        cols_used.extend([str(c) for c in exog_subset.columns])

    for i in range(int(max_lag), len(y_subset)):
        row: List[float] = []
        for lag in range(1, int(max_lag) + 1):
            row.append(float(vals_y[i - lag]))
        if vals_exog is not None:
            row.extend([float(v) for v in vals_exog[i].tolist()])

        X_list.append(row)
        y_list.append(float(vals_y[i]))

    X = np.asarray(X_list, dtype=float)
    y = np.asarray(y_list, dtype=float)
    return X, y, cols_used


def _scale_features_to_unit_box(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Scale each feature of X approximately into [-1, 1] (legacy behavior).

    Returns
    -------
    X_scaled, feat_min, feat_range
    """
    feat_min = X.min(axis=0)
    feat_max = X.max(axis=0)
    feat_range = feat_max - feat_min
    feat_range[feat_range == 0.0] = 1.0
    X_scaled = 2.0 * (X - feat_min) / feat_range - 1.0
    return X_scaled, feat_min, feat_range


def _future_bday_index(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return cast(pd.DatetimeIndex, pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"))


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def predict_pce_narx(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    exog_train_df: Optional[pd.DataFrame] = None,
    exog_future_df: Optional[pd.DataFrame] = None,
    progress_callback=None,
) -> Optional[pd.DataFrame]:
    """
    Train a sparse PCE-NARX model and forecast FH steps ahead.

    Output schema
    -------------
    DataFrame indexed by future business dates with columns:
      - PCE_Pred
      - PCE_Lower
      - PCE_Upper

    Notes
    -----
    - Optional dependencies: chaospy + scikit-learn.
    - If exog_train_df is provided, it is aligned to the target index and used as additional regressors.
    - If exog_future_df is missing but exog_train_df exists, the last exog row is repeated across FH.
    """
    if enriched_data is None or enriched_data.empty:
        return None

    # Feature gating via optional Constants flags (legacy-compatible)
    if not _discover_flag("PCE_ENABLED", True):
        return None

    cp, cp_expansion, LassoCV = _import_dependencies()
    if cp is None or LassoCV is None:
        return None

    tgt = str(target_col) if target_col else str(_discover_num("PCE_TARGET_COL", DEFAULT_TARGET_COL))
    if tgt not in enriched_data.columns:
        log.warning("PCE-NARX: target '%s' missing for %s.", tgt, ticker or "<ticker>")
        return None

    # Clean target series
    target_numeric = pd.to_numeric(enriched_data[tgt], errors="coerce")
    y_series = cast(pd.Series, target_numeric).dropna()
    if y_series.empty:
        return None
    y_series = _as_bday_series(y_series)

    # Clean and align exogenous data (optional)
    ex_train_aligned: Optional[pd.DataFrame] = None
    if exog_train_df is not None and not exog_train_df.empty:
        ex = exog_train_df.copy()
        if not isinstance(ex.index, pd.DatetimeIndex):
            ex.index = pd.to_datetime(ex.index, errors="coerce")
        ex = cast(pd.DataFrame, ex.sort_index())
        ex = cast(pd.DataFrame, ex.apply(pd.to_numeric, errors="coerce"))
        ex = cast(pd.DataFrame, ex.dropna(axis=1, how="all"))
        ex = cast(pd.DataFrame, ex.reindex(y_series.index).ffill())
        ex = cast(pd.DataFrame, ex.dropna(axis=0, how="any"))
        if not ex.empty:
            # Align y to ex index
            y2 = cast(pd.Series, y_series.reindex(ex.index)).dropna()
            ex2 = cast(pd.DataFrame, ex.reindex(y2.index)).dropna(axis=0, how="any")
            if not y2.empty and not ex2.empty:
                y_series = y2
                ex_train_aligned = ex2

    max_lag = int(_discover_num("PCE_LAGS", 5))

    X_opt, y_opt, cols_used = _build_narx_dataset_from_df(y_series, ex_train_aligned, max_lag)
    if X_opt is None or y_opt is None:
        log.warning("PCE-NARX: insufficient data after alignment for %s.", ticker or "<ticker>")
        return None

    X_arr = cast(np.ndarray, X_opt)
    y_arr = cast(np.ndarray, y_opt)

    min_samples = int(_discover_num("PCE_MIN_SAMPLES", 50))
    if len(X_arr) < min_samples:
        log.warning(
            "PCE-NARX: insufficient samples (%d) for %s. Need at least %d.",
            len(X_arr),
            ticker or "<ticker>",
            min_samples,
        )
        return None

    # Scale to [-1, 1]
    X_scaled, feat_min, feat_range = _scale_features_to_unit_box(X_arr)

    n_samples, n_features = X_arr.shape
    poly_degree = int(_discover_num("PCE_POLY_DEGREE", 2))

    # Independent uniform features in [-1, 1]
    dist = cp.Iid(cp.Uniform(-1.0, 1.0), int(n_features))

    # Polynomial expansion
    if cp_expansion is not None and hasattr(cp_expansion, "stieltjes"):
        poly_expansion = cp_expansion.stieltjes(int(poly_degree), dist)
    else:
        poly_expansion = cp.orth_ttr(int(poly_degree), dist)

    # Design matrix evaluation (compat across chaospy versions)
    try:
        A_train = cp.call(poly_expansion, X_scaled.T).T  # type: ignore[attr-defined]
    except Exception:
        A_train = cp.eval_polynomial(poly_expansion, X_scaled.T).T  # type: ignore[attr-defined]

    alphas = _discover_num("PCE_LASSO_ALPHAS", [1e-4, 1e-3, 1e-2])

    # Convergence remediation:
    # - Increase max_iter to reduce/avoid ConvergenceWarning from coordinate descent.
    # - Keep tol at sklearn default for stability; only allow more iterations to reach same optimum.
    lasso_max_iter = int(_discover_num("PCE_LASSO_MAX_ITER", DEFAULT_LASSO_MAX_ITER))

    try:
        lasso = LassoCV(  # type: ignore[call-arg]
            alphas=alphas,
            cv=3,
            n_jobs=1,
            random_state=42,
            max_iter=lasso_max_iter,
        )
        lasso.fit(A_train, y_arr)
    except Exception as e:
        log.warning("PCE-NARX: LassoCV fit failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Residual scale for intervals
    y_hat = lasso.predict(A_train)
    residuals = y_arr - y_hat
    sigma = float(np.std(residuals, ddof=1))
    if not np.isfinite(sigma) or sigma <= 0.0:
        sigma = float(np.std(y_arr) * 0.05)
        if not np.isfinite(sigma) or sigma <= 0.0:
            sigma = 1e-6

    fh_i = int(fh) if fh is not None else _discover_fh()
    fh_i = fh_i if fh_i > 0 else DEFAULT_FH

    # Future exogenous paths
    exog_future_vals: Optional[np.ndarray] = None
    if ex_train_aligned is not None and not ex_train_aligned.empty:
        if exog_future_df is not None and not exog_future_df.empty:
            exf = exog_future_df.copy()
            if not isinstance(exf.index, pd.DatetimeIndex):
                exf.index = pd.to_datetime(exf.index, errors="coerce")
            exf = cast(pd.DataFrame, exf.sort_index())
            exf = cast(pd.DataFrame, exf.apply(pd.to_numeric, errors="coerce"))
            exf = cast(pd.DataFrame, exf.dropna(axis=1, how="all"))
            exf = cast(pd.DataFrame, exf.reindex(columns=ex_train_aligned.columns))
            exf = cast(pd.DataFrame, exf.dropna(how="all"))
            if len(exf) < fh_i:
                log.warning(
                    "PCE-NARX: future exog length %d < FH %d for %s. Truncating FH.",
                    len(exf),
                    fh_i,
                    ticker or "<ticker>",
                )
                fh_i = int(len(exf))
            exog_future_vals = exf.to_numpy(dtype=float)[:fh_i, :]
        else:
            last_exog_row = ex_train_aligned.iloc[-1].to_numpy(dtype=float)
            exog_future_vals = np.tile(last_exog_row, (int(fh_i), 1))

    # Recursive multi-step forecast
    y_hist = [float(v) for v in y_series.to_numpy(dtype=float)]

    preds: List[float] = []
    lowers: List[float] = []
    uppers: List[float] = []

    z_score = float(_discover_num("PCE_ZSCORE", 1.645))

    for step in range(int(fh_i)):
        feats: List[float] = []
        for lag in range(1, int(max_lag) + 1):
            feats.append(float(y_hist[-lag]))

        if exog_future_vals is not None:
            feats.extend([float(v) for v in exog_future_vals[step].tolist()])

        z_vec = np.asarray(feats, dtype=float)
        z_scaled = 2.0 * (z_vec - feat_min) / feat_range - 1.0

        z_scaled_2d = z_scaled.reshape(int(n_features), 1)
        try:
            A_future = cp.call(poly_expansion, z_scaled_2d).T  # type: ignore[attr-defined]
        except Exception:
            A_future = cp.eval_polynomial(poly_expansion, z_scaled_2d).T  # type: ignore[attr-defined]

        try:
            y_pred = float(lasso.predict(A_future)[0])
        except Exception as e:
            log.warning("PCE-NARX: prediction failed for %s at step %d: %s", ticker or "<ticker>", step + 1, e)
            return None

        preds.append(y_pred)
        lowers.append(y_pred - z_score * sigma)
        uppers.append(y_pred + z_score * sigma)
        y_hist.append(y_pred)

        if progress_callback is not None:
            try:
                progress_callback(int(100.0 * (step + 1) / max(1, int(fh_i))), f"PCE-NARX step {step+1}/{fh_i}")
            except Exception:
                pass

    # Avoid pd.Timestamp(Index) ambiguity by using scalar max() first.
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, y_series.index.max())))
    future_dates = _future_bday_index(last_dt, int(fh_i))

    return pd.DataFrame(
        {"PCE_Pred": preds, "PCE_Lower": lowers, "PCE_Upper": uppers},
        index=future_dates,
    )


def predict_pce_narx_result(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    exog_train_df: Optional[pd.DataFrame] = None,
    exog_future_df: Optional[pd.DataFrame] = None,
    progress_callback=None,
) -> Optional[PCENARXResult]:
    """
    Convenience wrapper returning provenance alongside the prediction DataFrame.
    """
    tgt = str(target_col) if target_col else str(_discover_num("PCE_TARGET_COL", DEFAULT_TARGET_COL))
    max_lag = int(_discover_num("PCE_LAGS", 5))

    df = predict_pce_narx(
        enriched_data,
        ticker=ticker,
        target_col=tgt,
        fh=fh,
        exog_train_df=exog_train_df,
        exog_future_df=exog_future_df,
        progress_callback=progress_callback,
    )
    if df is None or df.empty:
        return None

    cols_used: List[str] = [f"y_lag{lag}" for lag in range(1, int(max_lag) + 1)]
    if exog_train_df is not None and not exog_train_df.empty:
        cols_used.extend([str(c) for c in exog_train_df.columns])

    meta: Dict[str, Any] = {
        "ticker": ticker,
        "target_col": tgt,
        "fh": int(fh) if fh is not None else _discover_fh(),
        "max_lag": int(max_lag),
        "poly_degree": int(_discover_num("PCE_POLY_DEGREE", 2)),
        "min_samples": int(_discover_num("PCE_MIN_SAMPLES", 50)),
        "has_exog": bool(exog_train_df is not None and not exog_train_df.empty),
        "lasso_max_iter": int(_discover_num("PCE_LASSO_MAX_ITER", DEFAULT_LASSO_MAX_ITER)),
    }

    return PCENARXResult(
        model_used="PCE-NARX",
        cols_used=tuple(cols_used),
        pred_df=df,
        meta=meta,
    )


__all__ = ["PCENARXResult", "predict_pce_narx", "predict_pce_narx_result"]
