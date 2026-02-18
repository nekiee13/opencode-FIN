# ------------------------
# src/models/arimax.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

import numpy as np
import pandas as pd

from src.exo.exo_validator import ValidationParams, validate_exo_config_for_run
from src.utils import compat as cap

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Constants / defaults
# ----------------------------------------------------------------------

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"

# Conservative SARIMAX spec (non-seasonal by default).
DEFAULT_ORDER: Tuple[int, int, int] = (1, 1, 1)
DEFAULT_SEASONAL_ORDER: Tuple[int, int, int, int] = (0, 0, 0, 0)

DEFAULT_COVERAGE = 0.90  # prediction interval coverage
_Z90 = 1.645  # ~90% two-sided z for normal approx


def _discover_fh() -> int:
    """
    Prefer Constants.FH when available, else fallback to DEFAULT_FH.
    """
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _get_target_col() -> str:
    try:
        import Constants as C  # type: ignore

        return str(getattr(C, "TARGET_COL", DEFAULT_TARGET_COL))
    except Exception:
        return DEFAULT_TARGET_COL


def _ensure_bday_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("ARIMAX requires a DatetimeIndex.")
    out = df.copy()
    out = cast(pd.DataFrame, out.sort_index())
    out = cast(pd.DataFrame, out.asfreq("B").ffill())
    return out


def _coerce_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _safe_reindex(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    out = df.reindex(index=index)
    out = cast(pd.DataFrame, out.ffill().bfill())
    return out


def _future_bdays(start: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    # start is last observed date; future begins on next business day
    return pd.date_range(
        start=start + pd.tseries.frequencies.to_offset("B"),
        periods=int(fh),
        freq="B",
    )


def _apply_exo_scenarios(
    *,
    model_name: str,
    ticker: str,
    exo_train_df: Optional[pd.DataFrame],
    exo_future_df: Optional[pd.DataFrame],
    exo_config: Optional[Dict[str, Any]],
    fh: int,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Applies scenario paths from exo_config to the future exogenous matrix.

    Semantics:
      - NONE : no scenario
      - DELTA: future = baseline_future + scenario_value_k
      - ABS  : future = scenario_value_k

    Baseline future:
      - If exo_future_df provided: use it (aligned & numeric coerced)
      - Else if exo_train_df provided: repeat last row fh times
      - Else: None (no exog)
    """
    if (exo_train_df is None or exo_train_df.empty) and (exo_future_df is None or exo_future_df.empty) and not exo_config:
        return None, None

    # Clean training exog
    train: Optional[pd.DataFrame] = None
    if exo_train_df is not None and not exo_train_df.empty:
        train_df = _coerce_numeric_frame(exo_train_df.copy())
        train_df = cast(pd.DataFrame, train_df.dropna(how="all"))
        train = None if train_df.empty else train_df

    # Clean future exog
    future: Optional[pd.DataFrame] = None
    if exo_future_df is not None and not exo_future_df.empty:
        future_df = _coerce_numeric_frame(exo_future_df.copy())
        future_df = cast(pd.DataFrame, future_df.dropna(how="all"))
        future = None if future_df.empty else future_df

    # Build baseline future from last training row when needed
    if future is None and train is not None and not train.empty:
        last_row = cast(pd.Series, train.iloc[-1])
        future = pd.DataFrame([last_row.values] * int(fh), columns=list(train.columns))

    if exo_config is None or future is None or future.empty:
        return train, future

    model_cfg = exo_config.get(model_name, {})
    ticker_cfg = model_cfg.get(ticker, {})
    if not isinstance(ticker_cfg, dict) or not ticker_cfg:
        return train, future

    out_future = future.copy()

    for regressor, spec in ticker_cfg.items():
        if not isinstance(spec, dict):
            continue
        if not bool(spec.get("enabled", False)):
            continue

        mode = str(spec.get("scenario_mode", "NONE")).upper()
        if mode not in ("NONE", "DELTA", "ABS"):
            continue
        if mode == "NONE":
            continue

        if regressor not in out_future.columns:
            continue

        values = list(spec.get("values", []))
        padded: List[Optional[float]] = (values + [None] * int(fh))[: int(fh)]

        base_col = pd.to_numeric(out_future[regressor], errors="coerce").to_numpy(dtype=float)
        new_col = base_col.copy()

        for i in range(int(fh)):
            v = padded[i]
            if v is None or not np.isfinite(v):
                continue
            if mode == "ABS":
                new_col[i] = float(v)
            else:  # DELTA
                if np.isfinite(new_col[i]):
                    new_col[i] = float(new_col[i] + float(v))
                else:
                    new_col[i] = float(v)

        out_future[regressor] = new_col

    return train, out_future


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class ARIMAXResult:
    pred_df: pd.DataFrame
    model_used: str
    cols_used: List[str]


def predict_arimax(
    df: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    exo_train_df: Optional[pd.DataFrame] = None,
    exo_future_df: Optional[pd.DataFrame] = None,
    exo_config: Optional[Dict[str, Any]] = None,
    validation_params: ValidationParams = ValidationParams(),
    order: Tuple[int, int, int] = DEFAULT_ORDER,
    seasonal_order: Tuple[int, int, int, int] = DEFAULT_SEASONAL_ORDER,
    enforce_stationarity: bool = False,
    enforce_invertibility: bool = False,
    coverage: float = DEFAULT_COVERAGE,
) -> Optional[ARIMAXResult]:
    """
    Fits SARIMAX with optional exogenous regressors and forecasts FH business days.

    Output:
      - pred_df columns: ARIMAX_Pred, ARIMAX_Lower, ARIMAX_Upper
      - index: future business dates
    """
    if df is None or df.empty:
        return None

    if not cap.HAS_STATSMODELS:
        log.warning("ARIMAX disabled: statsmodels is not available.")
        return None

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore
    except Exception as e:
        log.warning("ARIMAX disabled: could not import SARIMAX from statsmodels: %s", e)
        return None

    model_name = "ARIMAX"

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    tgt = str(target_col) if target_col else _get_target_col()
    if tgt not in df.columns:
        log.warning("ARIMAX: target column '%s' not found. cols=%s", tgt, list(df.columns))
        return None

    # Target series
    df_b = _ensure_bday_index(df)
    y_num = pd.to_numeric(df_b[tgt], errors="coerce")
    y = cast(pd.Series, y_num).dropna()
    if y.empty or len(y) < 30:
        log.warning("ARIMAX: insufficient target history after cleaning (n=%d).", len(y))
        return None

    train_index = y.index

    # Align training exog
    exo_train_aligned: Optional[pd.DataFrame] = None
    if exo_train_df is not None and not exo_train_df.empty:
        exo_train_df_b = _ensure_bday_index(exo_train_df)
        exo_train_df_b = _coerce_numeric_frame(exo_train_df_b)
        aligned = _safe_reindex(exo_train_df_b, train_index)
        aligned = cast(pd.DataFrame, aligned.dropna(axis=1, how="all"))
        exo_train_aligned = None if aligned.empty else aligned

    # Forecast index
    last_date = cast(pd.Timestamp, pd.Timestamp(train_index.max()))
    future_index = _future_bdays(last_date, fh_i)

    # Align future exog
    exo_future_aligned: Optional[pd.DataFrame] = None
    if exo_future_df is not None and not exo_future_df.empty:
        exo_future_df2 = exo_future_df.copy()
        if isinstance(exo_future_df2.index, pd.DatetimeIndex) and exo_future_df2.index.notna().all():
            exo_future_df2 = _coerce_numeric_frame(exo_future_df2)
            aligned_f = _safe_reindex(exo_future_df2, future_index)
        else:
            tmp = _coerce_numeric_frame(exo_future_df2).reset_index(drop=True)
            aligned_f = tmp.iloc[:fh_i].copy()
            aligned_f.index = future_index  # type: ignore[assignment]
        aligned_f = cast(pd.DataFrame, aligned_f.dropna(axis=1, how="all"))
        exo_future_aligned = None if aligned_f.empty else aligned_f

    # Apply scenario paths
    exo_train_final, exo_future_final = _apply_exo_scenarios(
        model_name=model_name,
        ticker=str(ticker),
        exo_train_df=exo_train_aligned,
        exo_future_df=exo_future_aligned,
        exo_config=exo_config,
        fh=fh_i,
    )

    # Consistency: when training exog is absent, future exog is dropped for ARIMAX.
    if exo_train_final is None:
        exo_future_final = None

    # Optional ABS validation (warnings only)
    try:
        if exo_config and exo_train_final is not None:
            validate_exo_config_for_run(
                ticker=str(ticker),
                model_name=model_name,
                enriched_data=exo_train_final,  # proxy for enriched regressor history
                target_index=train_index,
                exo_config=cast(Dict[str, Any], exo_config),
                params=validation_params,
            )
    except Exception as e:
        log.debug("ARIMAX: exo validation failed (non-fatal): %s", e, exc_info=True)

    # Fit SARIMAX
    try:
        mod = SARIMAX(
            endog=y,
            exog=exo_train_final,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=enforce_stationarity,
            enforce_invertibility=enforce_invertibility,
        )
        # statsmodels typing stubs are frequently incomplete; Any cast prevents false attribute errors.
        res = cast(Any, mod.fit(disp=False))
    except Exception as e:
        log.warning("ARIMAX: model fit failed for %s: %s", ticker, e, exc_info=True)
        return None

    # Forecast
    try:
        fc = cast(Any, res.get_forecast(steps=fh_i, exog=exo_future_final))
        pred_mean = cast(pd.Series, fc.predicted_mean)

        lower: Optional[pd.Series] = None
        upper: Optional[pd.Series] = None

        # Prefer conf_int when available
        try:
            alpha = float(max(1e-6, min(0.99, 1.0 - float(coverage))))
            ci = fc.conf_int(alpha=alpha)
            if isinstance(ci, pd.DataFrame) and ci.shape[1] >= 2:
                lower = cast(pd.Series, ci.iloc[:, 0])
                upper = cast(pd.Series, ci.iloc[:, 1])
        except Exception:
            lower = None
            upper = None

        pred_mean.index = future_index

        if lower is None or upper is None:
            # Fallback: normal approximation using residual std
            resid_raw = getattr(res, "resid", None)
            resid_s = cast(pd.Series, pd.Series(resid_raw)).dropna() if resid_raw is not None else pd.Series(dtype=float)
            sigma = float(np.std(resid_s.to_numpy(dtype=float), ddof=1)) if len(resid_s) > 2 else 0.0
            if not np.isfinite(sigma) or sigma <= 0.0:
                sigma = float(np.std(y.to_numpy(dtype=float), ddof=1) * 0.05)

            z = _Z90
            lower = pred_mean - z * sigma
            upper = pred_mean + z * sigma
        else:
            lower = cast(pd.Series, lower)
            upper = cast(pd.Series, upper)
            lower.index = future_index
            upper.index = future_index

        out_df = pd.DataFrame(
            {
                "ARIMAX_Pred": pd.to_numeric(pred_mean, errors="coerce"),
                "ARIMAX_Lower": pd.to_numeric(lower, errors="coerce"),
                "ARIMAX_Upper": pd.to_numeric(upper, errors="coerce"),
            },
            index=future_index,
        )

        cols_used: List[str] = ["ARIMAX_Pred", "ARIMAX_Lower", "ARIMAX_Upper"]
        return ARIMAXResult(pred_df=out_df, model_used=model_name, cols_used=cols_used)

    except Exception as e:
        log.warning("ARIMAX: forecast failed for %s: %s", ticker, e, exc_info=True)
        return None


# ----------------------------------------------------------------------
# Legacy-friendly adapter (optional)
# ----------------------------------------------------------------------

def predict_arima(
    df: pd.DataFrame,
    *,
    ticker: str = "",
    exo_config: Optional[Dict[str, Any]] = None,
    exo_train_df: Optional[pd.DataFrame] = None,
    exo_future_df: Optional[pd.DataFrame] = None,
) -> Tuple[Optional[pd.DataFrame], str, List[str]]:
    """
    Compatibility adapter for older call sites.

    Returns:
      (pred_df_or_none, model_name, cols_used)

    model_name is:
      - "ARIMAX" when successful
      - "ARIMAX_DISABLED" when statsmodels is unavailable
      - "ARIMAX_FAILED" otherwise
    """
    r = predict_arimax(
        df,
        ticker=ticker,
        exo_config=exo_config,
        exo_train_df=exo_train_df,
        exo_future_df=exo_future_df,
    )
    if r is None:
        if not cap.HAS_STATSMODELS:
            return None, "ARIMAX_DISABLED", []
        return None, "ARIMAX_FAILED", []
    return r.pred_df, r.model_used, r.cols_used


__all__ = ["ARIMAXResult", "predict_arimax", "predict_arima"]
