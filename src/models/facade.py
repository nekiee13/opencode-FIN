# ------------------------
# src/models/facade.py
# ------------------------

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"


# ----------------------------------------------------------------------
# Small utilities (Constants-aware, but safe if Constants is absent)
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
    """
    Sort + coerce to business-day frequency with forward-fill.
    """
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Model facade requires DatetimeIndex input.")
    out = cast(pd.DataFrame, df.copy())
    out = cast(pd.DataFrame, out.sort_index())
    out = cast(pd.DataFrame, out.asfreq("B").ffill())
    return out


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if np.isfinite(v):
            return v
        return None
    except Exception:
        return None


def _ensure_datetime_index(idx: pd.Index) -> pd.DatetimeIndex:
    """
    Force a DatetimeIndex or raise (Pylance-friendly).
    """
    if isinstance(idx, pd.DatetimeIndex):
        return idx
    coerced = pd.to_datetime(idx, errors="coerce")
    dt_idx = pd.DatetimeIndex(coerced)
    if dt_idx.isna().any():
        raise ValueError("Index contains non-datetime values.")
    return dt_idx


def _ensure_timestamp(x: Any) -> pd.Timestamp:
    """
    Force a pandas Timestamp from a scalar-like input.

    Notes:
    - Pylance often treats Index/Hashable as incompatible for pd.Timestamp.
    - This function ensures scalar extraction first, then conversion.
    """
    if isinstance(x, pd.Timestamp):
        return x
    if isinstance(x, (np.datetime64,)):
        return pd.Timestamp(x)
    if hasattr(x, "to_pydatetime"):
        # Covers Timestamp-like objects
        try:
            return pd.Timestamp(x.to_pydatetime())
        except Exception:
            pass
    return pd.Timestamp(pd.to_datetime(x))


def _coerce_pred_df(obj: Any, *, default_col: str) -> Optional[pd.DataFrame]:
    """
    Normalize a model output into a DataFrame indexed by future dates.

    Accepts:
      - DataFrame
      - Series
      - array-like convertible to DataFrame

    Returns None on failure.
    """
    if obj is None:
        return None

    if isinstance(obj, pd.DataFrame):
        out_df = cast(pd.DataFrame, obj.copy())
    elif isinstance(obj, pd.Series):
        out_df = cast(pd.DataFrame, obj.to_frame(name=default_col))
    else:
        try:
            out_df = cast(pd.DataFrame, pd.DataFrame(obj))
        except Exception:
            return None

    if out_df.empty:
        return None

    if not isinstance(out_df.index, pd.DatetimeIndex):
        # Try coercion, but fail deterministically if impossible
        try:
            out_df.index = _ensure_datetime_index(cast(pd.Index, out_df.index))
        except Exception:
            return None

    return out_df


# ----------------------------------------------------------------------
# Forecast result structures
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ForecastArtifact:
    """
    Phase-1 normalized forecast payload.

    Required:
      - pred_df: DataFrame indexed by future dates (DatetimeIndex)
      - pred_col: name of the point forecast column inside pred_df
    """

    pred_df: pd.DataFrame
    pred_col: str

    model: str = "UNKNOWN"
    lower_col: Optional[str] = None
    upper_col: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.pred_df is None or self.pred_df.empty:
            raise ValueError("ForecastArtifact.pred_df must be non-empty.")

        if not isinstance(self.pred_df, pd.DataFrame):
            raise TypeError("ForecastArtifact.pred_df must be a pandas DataFrame.")

        if self.pred_col not in self.pred_df.columns:
            raise ValueError(
                f"ForecastArtifact.pred_col '{self.pred_col}' not in pred_df.columns={list(self.pred_df.columns)}"
            )

        if not isinstance(self.pred_df.index, pd.DatetimeIndex):
            raise ValueError("ForecastArtifact.pred_df index must be a DatetimeIndex.")

    @property
    def df(self) -> pd.DataFrame:
        # Backward-compat convenience: older code used artifact.df
        return self.pred_df


@dataclass(frozen=True)
class ForecastBundle:
    """
    A bundle of optional forecasts for a ticker.
    """

    ticker: str
    fh: int
    forecasts: Dict[str, ForecastArtifact]  # model_name -> artifact
    warnings: List[str]


# ----------------------------------------------------------------------
# Model adapters (import-local to keep optional deps safe)
# ----------------------------------------------------------------------


def run_ets(
    df: pd.DataFrame,
    *,
    ticker: str,
    fh: Optional[int] = None,
) -> Optional[ForecastArtifact]:
    try:
        from src.models.ets import predict_ets  # type: ignore
    except Exception as e:
        log.warning("ETS import failed: %s", e)
        return None

    r = predict_ets(df, ticker=ticker, fh=fh)
    if r is None:
        return None

    out_df = _coerce_pred_df(getattr(r, "pred_df", r), default_col="ETS_Pred")
    if out_df is None:
        return None

    out_df = cast(pd.DataFrame, out_df.copy())

    return ForecastArtifact(
        pred_df=cast(pd.DataFrame, out_df),
        pred_col="ETS_Pred"
        if "ETS_Pred" in out_df.columns
        else cast(str, out_df.columns[0]),
        model="ETS",
        lower_col="ETS_Lower" if "ETS_Lower" in out_df.columns else None,
        upper_col="ETS_Upper" if "ETS_Upper" in out_df.columns else None,
        meta={
            "cols_used": getattr(r, "cols_used", None),
            "model_used": getattr(r, "model_used", None),
        },
    )


def _call_predict_arimax_compat(
    predict_arimax: Any,
    df: pd.DataFrame,
    *,
    ticker: str,
    exog_train: Optional[pd.DataFrame],
    exog_future: Optional[pd.DataFrame],
    fh: Optional[int],
) -> Any:
    """
    Runtime-safe call wrapper.

    - Signature is introspected when possible and called using supported names.
    - Positional fallbacks are attempted for maximum compatibility.
    """
    try:
        sig = inspect.signature(predict_arimax)
        params = sig.parameters

        kwargs: Dict[str, Any] = {}
        if "ticker" in params:
            kwargs["ticker"] = ticker
        if "fh" in params and fh is not None:
            kwargs["fh"] = int(fh)

        if "exog_train" in params:
            kwargs["exog_train"] = exog_train
        elif "exog_train_df" in params:
            kwargs["exog_train_df"] = exog_train
        elif "X_train" in params:
            kwargs["X_train"] = exog_train

        if "exog_future" in params:
            kwargs["exog_future"] = exog_future
        elif "exog_future_df" in params:
            kwargs["exog_future_df"] = exog_future
        elif "X_future" in params:
            kwargs["X_future"] = exog_future

        return predict_arimax(df, **kwargs)

    except Exception:
        # Positional fallbacks
        try:
            return predict_arimax(df, ticker, exog_train, exog_future, fh)
        except Exception:
            try:
                return predict_arimax(df, ticker, fh)
            except Exception:
                return predict_arimax(df)


def run_arimax(
    df: pd.DataFrame,
    *,
    ticker: str,
    exog_train: Optional[pd.DataFrame] = None,
    exog_future: Optional[pd.DataFrame] = None,
    fh: Optional[int] = None,
) -> Optional[ForecastArtifact]:
    """
    Facade expects a canonical ARIMAX implementation at src/models/arimax.py.

    Supports:
      - returning an object with pred_df/pred_col/lower_col/upper_col/meta
      - returning a DataFrame (or Series) directly
    """
    try:
        from src.models.arimax import predict_arimax  # type: ignore
    except Exception as e:
        log.warning("ARIMAX import failed (expected during migration): %s", e)
        return None

    try:
        r = _call_predict_arimax_compat(
            predict_arimax,
            df,
            ticker=ticker,
            exog_train=exog_train,
            exog_future=exog_future,
            fh=fh,
        )
    except Exception as e:
        log.warning("ARIMAX failed for %s: %s", ticker, e, exc_info=True)
        return None

    if r is None:
        return None

    # Normalize any return type into a DataFrame
    if isinstance(r, pd.DataFrame):
        out_df = cast(pd.DataFrame, r.copy())
        pred_col = (
            "ARIMAX_Pred"
            if "ARIMAX_Pred" in out_df.columns
            else cast(str, out_df.columns[0])
        )
        return ForecastArtifact(
            pred_df=cast(pd.DataFrame, out_df),
            pred_col=pred_col,
            model="ARIMAX",
            lower_col="ARIMAX_Lower" if "ARIMAX_Lower" in out_df.columns else None,
            upper_col="ARIMAX_Upper" if "ARIMAX_Upper" in out_df.columns else None,
            meta={},
        )

    if isinstance(r, pd.Series):
        out_df = cast(pd.DataFrame, r.to_frame(name="ARIMAX_Pred"))
        return ForecastArtifact(
            pred_df=cast(pd.DataFrame, out_df),
            pred_col="ARIMAX_Pred",
            model="ARIMAX",
            lower_col=None,
            upper_col=None,
            meta={},
        )

    out_df_obj = getattr(r, "pred_df", None)
    pred_col_obj = getattr(r, "pred_col", "ARIMAX_Pred")

    out_df = _coerce_pred_df(out_df_obj, default_col=str(pred_col_obj))
    if out_df is None:
        return None

    pred_col = (
        str(pred_col_obj)
        if str(pred_col_obj) in out_df.columns
        else cast(str, out_df.columns[0])
    )
    lower_col = cast(Optional[str], getattr(r, "lower_col", None))
    upper_col = cast(Optional[str], getattr(r, "upper_col", None))
    meta_obj = getattr(r, "meta", {})
    meta = cast(Dict[str, Any], meta_obj) if isinstance(meta_obj, dict) else {}

    return ForecastArtifact(
        pred_df=cast(pd.DataFrame, out_df),
        pred_col=pred_col,
        model="ARIMAX",
        lower_col=lower_col if lower_col in out_df.columns else None,
        upper_col=upper_col if upper_col in out_df.columns else None,
        meta=meta,
    )


def run_random_walk(
    df: pd.DataFrame,
    *,
    ticker: str,
    fh: Optional[int] = None,
    target_col: Optional[str] = None,
) -> Optional[ForecastArtifact]:
    """
    Minimal Random Walk baseline to keep the facade functional.
    Produces RW_Pred/RW_Lower/RW_Upper using a residual-scale heuristic.
    """
    fh_i = int(fh) if fh is not None else _discover_fh()
    tgt = str(target_col) if target_col else _discover_target_col()

    if df is None or df.empty or tgt not in df.columns:
        return None

    df_b = _as_bday(df)
    y = cast(pd.Series, pd.to_numeric(df_b[tgt], errors="coerce")).dropna()
    if y.empty or len(y) < 10:
        return None

    # Ensure DatetimeIndex is treated as such by type checkers
    y_idx = _ensure_datetime_index(cast(pd.Index, y.index))
    last_dt = _ensure_timestamp(y_idx[-1])

    last = float(y.iloc[-1])

    diffs = np.diff(y.to_numpy(dtype=float))
    sigma = (
        float(np.std(diffs, ddof=1))
        if diffs.size > 2
        else float(np.std(y.to_numpy(dtype=float), ddof=1) * 0.05)
    )
    if not np.isfinite(sigma) or sigma <= 0.0:
        sigma = max(abs(last) * 0.01, 1e-6)

    z = 1.645  # ~90%
    start = last_dt + pd.offsets.BDay(1)
    future_index = pd.date_range(start=start, periods=fh_i, freq="B")

    preds = np.full(shape=(fh_i,), fill_value=last, dtype=float)
    lower = preds - z * sigma
    upper = preds + z * sigma

    out_df = pd.DataFrame(
        {"RW_Pred": preds, "RW_Lower": lower, "RW_Upper": upper},
        index=future_index,
    )

    return ForecastArtifact(
        pred_df=cast(pd.DataFrame, out_df),
        pred_col="RW_Pred",
        model="RW",
        lower_col="RW_Lower",
        upper_col="RW_Upper",
        meta={"note": "Random Walk baseline (flat forecast at last close)."},
    )


def run_pce_narx(
    df: pd.DataFrame,
    *,
    ticker: str,
    exog_train: Optional[pd.DataFrame] = None,
    exog_future: Optional[pd.DataFrame] = None,
) -> Optional[ForecastArtifact]:
    """
    Optional PCE-NARX.

    Expected canonical implementation:
      - src/models/pce_narx.py
    Fallback legacy compat:
      - compat/PCEModel.py (imported as PCEModel via compat on sys.path)
    """
    predict_pce_narx: Optional[Any] = None

    try:
        from src.models.pce_narx import predict_pce_narx as _p  # type: ignore

        predict_pce_narx = _p
    except Exception:
        predict_pce_narx = None

    if predict_pce_narx is None:
        try:
            import PCEModel  # type: ignore

            predict_pce_narx = getattr(PCEModel, "predict_pce_narx", None)
        except Exception:
            predict_pce_narx = None

    if predict_pce_narx is None:
        return None

    try:
        try:
            out_obj = predict_pce_narx(
                enriched_data=df,
                exog_train_df=exog_train,
                exog_future_df=exog_future,
            )
        except TypeError:
            out_obj = predict_pce_narx(df, exog_train, exog_future)
    except Exception as e:
        log.warning("PCE-NARX failed for %s: %s", ticker, e, exc_info=True)
        return None

    out_df = _coerce_pred_df(out_obj, default_col="PCE_Pred")
    if out_df is None:
        return None

    pred_col = (
        "PCE_Pred" if "PCE_Pred" in out_df.columns else cast(str, out_df.columns[0])
    )

    return ForecastArtifact(
        pred_df=cast(pd.DataFrame, out_df.copy()),
        pred_col=pred_col,
        model="PCE",
        lower_col="PCE_Lower" if "PCE_Lower" in out_df.columns else None,
        upper_col="PCE_Upper" if "PCE_Upper" in out_df.columns else None,
        meta={"note": "Sparse PCE-NARX (optional dependency gated)."},
    )


def run_dynamix(
    df: pd.DataFrame,
    *,
    ticker: str,
    fh: Optional[int] = None,
    target_col: Optional[str] = None,
) -> Optional[ForecastArtifact]:
    try:
        from src.models.dynamix import predict_dynamix  # type: ignore
    except Exception as e:
        log.warning("DynaMix import failed: %s", e)
        return None

    try:
        out = predict_dynamix(df, ticker=ticker, target_col=target_col, fh=fh)
    except Exception as e:
        log.warning("DynaMix failed for %s: %s", ticker, e, exc_info=True)
        return None

    if out is None:
        return None

    out_df = _coerce_pred_df(out, default_col="DYNAMIX_Pred")
    if out_df is None:
        return None

    out_df = cast(pd.DataFrame, out_df.copy())

    pred_col = (
        "DYNAMIX_Pred"
        if "DYNAMIX_Pred" in out_df.columns
        else cast(str, out_df.columns[0])
    )

    return ForecastArtifact(
        pred_df=cast(pd.DataFrame, out_df),
        pred_col=pred_col,
        model="DYNAMIX",
        lower_col="DYNAMIX_Lower" if "DYNAMIX_Lower" in out_df.columns else None,
        upper_col="DYNAMIX_Upper" if "DYNAMIX_Upper" in out_df.columns else None,
        meta={"cpu_only": True},
    )


# ----------------------------------------------------------------------
# Public facade API
# ----------------------------------------------------------------------

MODEL_PRIORITY_DEFAULT: Sequence[str] = ("DYNAMIX", "ARIMAX", "ETS", "PCE", "RW")


def compute_forecasts(
    df: pd.DataFrame,
    *,
    ticker: str,
    fh: Optional[int] = None,
    exog_train: Optional[pd.DataFrame] = None,
    exog_future: Optional[pd.DataFrame] = None,
    enabled_models: Optional[Sequence[str]] = None,
) -> ForecastBundle:
    """
    Run a set of models (best-effort) and return a normalized bundle.

    Notes:
    - No model is mandatory; the bundle may be empty.
    - No selection occurs here; use select_forecast_path().
    """
    fh_i = int(fh) if fh is not None else _discover_fh()
    allow = set(m.upper() for m in (enabled_models or MODEL_PRIORITY_DEFAULT))

    forecasts: Dict[str, ForecastArtifact] = {}
    warnings_list: List[str] = []

    df_b = _as_bday(df)

    if "DYNAMIX" in allow:
        d = run_dynamix(df_b, ticker=ticker, fh=fh_i)
        if d is not None:
            forecasts["DYNAMIX"] = d
        else:
            warnings_list.append("DYNAMIX unavailable or failed.")

    if "ARIMAX" in allow:
        a = run_arimax(
            df_b, ticker=ticker, exog_train=exog_train, exog_future=exog_future, fh=fh_i
        )
        if a is not None:
            forecasts["ARIMAX"] = a
        else:
            warnings_list.append("ARIMAX unavailable or failed.")

    if "ETS" in allow:
        e = run_ets(df_b, ticker=ticker, fh=fh_i)
        if e is not None:
            forecasts["ETS"] = e
        else:
            warnings_list.append("ETS unavailable or failed.")

    if "PCE" in allow:
        p = run_pce_narx(
            df_b, ticker=ticker, exog_train=exog_train, exog_future=exog_future
        )
        if p is not None:
            if len(p.pred_df) >= fh_i:
                p_df = cast(pd.DataFrame, p.pred_df.iloc[:fh_i].copy())
                forecasts["PCE"] = ForecastArtifact(
                    pred_df=cast(pd.DataFrame, p_df),
                    pred_col=p.pred_col,
                    model=p.model,
                    lower_col=p.lower_col,
                    upper_col=p.upper_col,
                    meta=p.meta,
                )
            else:
                warnings_list.append(
                    f"PCE produced FH={len(p.pred_df)} < requested FH={fh_i}; omitted."
                )
        else:
            warnings_list.append("PCE unavailable or failed.")

    if "RW" in allow:
        r = run_random_walk(df_b, ticker=ticker, fh=fh_i)
        if r is not None:
            forecasts["RW"] = r
        else:
            warnings_list.append("RW unavailable or failed (unexpected).")

    return ForecastBundle(
        ticker=ticker, fh=fh_i, forecasts=forecasts, warnings=warnings_list
    )


def select_forecast_path(
    bundle: ForecastBundle,
    *,
    model_priority: Sequence[str] = MODEL_PRIORITY_DEFAULT,
) -> Tuple[str, ForecastArtifact]:
    """
    Select the first available model in model_priority.

    Raises RuntimeError if bundle has no forecasts.
    """
    if bundle is None or not bundle.forecasts:
        raise RuntimeError(
            f"{getattr(bundle, 'ticker', '')}: no forecasts available to select from."
        )

    for m in model_priority:
        key = str(m).upper()
        if key in bundle.forecasts:
            return key, bundle.forecasts[key]

    key0 = sorted(bundle.forecasts.keys())[0]
    return key0, bundle.forecasts[key0]


def make_fh_table_row(
    *,
    ticker: str,
    artifact: ForecastArtifact,
    last_close: Optional[float],
    fh: int,
) -> Dict[str, Any]:
    """
    Create a standard FH row suitable for FH table generation.

    Columns produced (stable):
      Ticker, Last_Close_ASOF, Model_Used, Col_Used,
      FH_Date1, FH_Day1, FH_Date2, FH_Day2, FH_Date3, FH_Day3
    """
    df = cast(pd.DataFrame, artifact.pred_df.copy())
    ser = cast(pd.Series, df[artifact.pred_col]).iloc[:fh]

    if len(ser) != fh:
        raise RuntimeError(
            f"{ticker}: expected FH={fh}, got {len(ser)} from {artifact.model}/{artifact.pred_col}"
        )

    dt_idx = _ensure_datetime_index(cast(pd.Index, ser.index))

    def ymd(i: int) -> str:
        ts = _ensure_timestamp(dt_idx[i])
        return ts.strftime("%Y-%m-%d")

    def val(i: int) -> Optional[float]:
        return _safe_float(ser.iloc[i])

    out: Dict[str, Any] = {
        "Ticker": ticker,
        "Last_Close_ASOF": float(last_close) if last_close is not None else np.nan,
        "Model_Used": artifact.model,
        "Col_Used": artifact.pred_col,
        "FH_Date1": ymd(0),
        "FH_Day1": val(0),
        "FH_Date2": ymd(1),
        "FH_Day2": val(1),
        "FH_Date3": ymd(2),
        "FH_Day3": val(2),
    }
    return out


# ----------------------------------------------------------------------
# Capability summary (LAZY IMPORT to satisfy Phase-1 import safety)
# ----------------------------------------------------------------------


def capabilities_summary() -> Dict[str, Any]:
    """
    Convenience: expose capability flags relevant to the facade.

    Phase-1 safety requirement:
    - Optional/heavy deps must not be imported at src.models.facade import-time.
    - Therefore, src.utils.compat is imported lazily here and degraded gracefully if blocked.
    """
    try:
        from src.utils import compat as _cap  # local import by design

        return {
            "HAS_NUMPY": bool(getattr(_cap, "HAS_NUMPY", False)),
            "HAS_PANDAS": bool(getattr(_cap, "HAS_PANDAS", False)),
            "HAS_STATSMODELS": bool(getattr(_cap, "HAS_STATSMODELS", False)),
            "HAS_ARCH": bool(getattr(_cap, "HAS_ARCH", False)),
            "HAS_TORCH": bool(getattr(_cap, "HAS_TORCH", False)),
            "HAS_TENSORFLOW": bool(getattr(_cap, "HAS_TENSORFLOW", False)),
            "HAS_TDA": bool(getattr(_cap, "HAS_TDA", False)),
            "CAPABILITIES": dict(getattr(_cap, "CAPABILITIES", {})),
        }
    except Exception:
        return {
            "HAS_NUMPY": True,  # numpy is required by this module itself
            "HAS_PANDAS": True,  # pandas is required by this module itself
            "HAS_STATSMODELS": False,
            "HAS_ARCH": False,
            "HAS_TORCH": False,
            "HAS_TENSORFLOW": False,
            "HAS_TDA": False,
            "CAPABILITIES": {},
        }


__all__ = [
    "ForecastArtifact",
    "ForecastBundle",
    "MODEL_PRIORITY_DEFAULT",
    "compute_forecasts",
    "select_forecast_path",
    "make_fh_table_row",
    "capabilities_summary",
]
