# ------------------------
# src/models/lstm.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from src.utils import compat as cap

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"


# ----------------------------------------------------------------------
# Result structure
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class LSTMResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "LSTM_Pred"
    lower_col: str = "LSTM_Lower"
    upper_col: str = "LSTM_Upper"
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
        raise ValueError("LSTM model requires DatetimeIndex input.")
    out = df.copy()
    out = cast(pd.DataFrame, out.sort_index())
    out = cast(pd.DataFrame, out.asfreq("B").ffill())
    return out


def _future_index(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return cast(pd.DatetimeIndex, pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"))


# ----------------------------------------------------------------------
# Pinball loss for quantile regression (TF-loaded lazily)
# ----------------------------------------------------------------------

def _pinball_loss(q: float):
    """
    Returns a tf.keras loss function implementing pinball loss for quantile q.
    TensorFlow symbols are resolved at runtime (lazy import).
    """
    qf = float(q)

    def loss(y_true, y_pred):
        import tensorflow as tf  # type: ignore

        e = y_true - y_pred
        return tf.reduce_mean(tf.maximum(qf * e, (qf - 1.0) * e))

    return loss


# ----------------------------------------------------------------------
# Dataset utilities
# ----------------------------------------------------------------------

def _build_supervised_windows(
    X: np.ndarray,
    y: np.ndarray,
    lookback: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create (samples, lookback, n_features) and (samples, 1) arrays.
    """
    if X.ndim != 2:
        raise ValueError("X must be 2D.")
    if y.ndim != 1:
        raise ValueError("y must be 1D.")
    if len(X) != len(y):
        raise ValueError("X and y must have same length.")
    if len(y) <= int(lookback):
        return np.empty((0, int(lookback), X.shape[1])), np.empty((0, 1))

    xs: list[np.ndarray] = []
    ys: list[list[float]] = []
    for i in range(int(lookback), len(y)):
        xs.append(X[i - int(lookback) : i, :])
        ys.append([float(y[i])])

    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def _scale_minmax_fit(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fit a simple min-max scaler on columns of X.
    Returns X_scaled, x_min, x_range.
    """
    x_min = np.nanmin(X, axis=0)
    x_max = np.nanmax(X, axis=0)
    x_range = x_max - x_min
    x_range[x_range == 0.0] = 1.0
    X_scaled = (X - x_min) / x_range
    return X_scaled, x_min, x_range


def _scale_minmax_apply(X: np.ndarray, x_min: np.ndarray, x_range: np.ndarray) -> np.ndarray:
    return (X - x_min) / x_range


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def predict_lstm_quantiles(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    exog_train: Optional[pd.DataFrame] = None,
    exog_future: Optional[pd.DataFrame] = None,
    quantiles: Tuple[float, float] = (0.10, 0.90),
    lookback: int = 60,
    epochs: int = 60,
    batch_size: int = 32,
    lstm_units: int = 64,
    dense_units: int = 32,
    dropout: float = 0.10,
    learning_rate: float = 1e-3,
    min_samples: int = 200,
    seed: int = 42,
    verbose: int = 0,
) -> Optional[LSTMResult]:
    """
    Quantile LSTM forecaster.

    Output
    ------
    DataFrame indexed by future business dates with columns:
      - LSTM_Pred  (midpoint of quantile heads)
      - LSTM_Lower (q_lo)
      - LSTM_Upper (q_hi)

    Notes
    -----
    - TensorFlow is optional. If missing, returns None.
    - Exogenous regressors are optional. If provided, they are concatenated as extra features.
    - Forecast is recursive: predicted point estimate feeds into the next step.
    """
    if not cap.HAS_TENSORFLOW:
        log.info("LSTM disabled: optional dependency 'tensorflow' not available.")
        return None

    # Lazy TF import (keeps module import-safe)
    try:
        import tensorflow as tf  # type: ignore
        from tensorflow import keras  # type: ignore
    except Exception as e:
        log.warning("LSTM disabled: could not import tensorflow/keras: %s", e)
        return None

    if enriched_data is None or enriched_data.empty:
        return None

    tgt = str(target_col) if target_col else _discover_target_col()
    fh_i = int(fh) if fh is not None else _discover_fh()
    fh_i = fh_i if fh_i > 0 else DEFAULT_FH

    q_lo, q_hi = float(quantiles[0]), float(quantiles[1])
    if not (0.0 < q_lo < q_hi < 1.0):
        raise ValueError("quantiles must satisfy 0 < q_lo < q_hi < 1.")

    if tgt not in enriched_data.columns:
        log.warning("LSTM: target column '%s' missing for %s.", tgt, ticker or "<ticker>")
        return None

    # Determinism (best effort)
    np.random.seed(int(seed))
    try:
        tf.random.set_seed(int(seed))
    except Exception:
        pass

    df_b = _as_bday(enriched_data)

    # Prepare target series
    y_ser = cast(pd.Series, pd.to_numeric(df_b[tgt], errors="coerce")).dropna()
    if y_ser.empty:
        return None

    min_need = max(int(min_samples), int(lookback) + 25)
    if len(y_ser) < min_need:
        log.warning(
            "LSTM: insufficient samples (%d) for %s. Need at least ~%d.",
            len(y_ser),
            ticker or "<ticker>",
            min_need,
        )
        return None

    # Align exogenous regressors (optional)
    ex_train_aligned: Optional[pd.DataFrame] = None
    if exog_train is not None and not exog_train.empty:
        ex = exog_train.copy()
        if not isinstance(ex.index, pd.DatetimeIndex):
            raise ValueError("exog_train must have a DatetimeIndex.")
        ex = cast(pd.DataFrame, ex.sort_index())
        ex = cast(pd.DataFrame, ex.reindex(y_ser.index))
        ex = cast(pd.DataFrame, ex.apply(pd.to_numeric, errors="coerce"))
        ex = cast(pd.DataFrame, ex.dropna(axis=1, how="all"))
        ex = cast(pd.DataFrame, ex.ffill())
        ex = cast(pd.DataFrame, ex.dropna(axis=0, how="any"))

        if not ex.empty:
            # Align y to ex index
            y2 = y_ser.reindex(ex.index).dropna()
            ex2 = cast(pd.DataFrame, ex.reindex(y2.index)).dropna(axis=0, how="any")
            if not y2.empty and not ex2.empty:
                y_ser = y2
                ex_train_aligned = ex2

    # Feature matrix: [target] + exog columns (if any)
    feat_cols: list[str] = [tgt]
    X_df = pd.DataFrame(index=y_ser.index)
    X_df[tgt] = y_ser

    if ex_train_aligned is not None and not ex_train_aligned.empty:
        for c in ex_train_aligned.columns:
            cn = str(c)
            X_df[cn] = ex_train_aligned[c]
            feat_cols.append(cn)

    X_df = cast(pd.DataFrame, X_df.dropna(how="any"))
    y_ser = cast(pd.Series, X_df[tgt])

    if len(X_df) < min_need:
        log.warning(
            "LSTM: insufficient samples after alignment (%d) for %s.",
            len(X_df),
            ticker or "<ticker>",
        )
        return None

    # Numpy arrays (raw space)
    X_raw = X_df.to_numpy(dtype=float)
    y_raw = y_ser.to_numpy(dtype=float)

    # Scale features to [0,1]
    X_scaled, x_min, x_range = _scale_minmax_fit(X_raw)

    # Supervised windows
    X_win, y_win = _build_supervised_windows(X_scaled, y_raw, lookback=int(lookback))
    if X_win.size == 0 or y_win.size == 0:
        log.warning("LSTM: could not build supervised windows for %s.", ticker or "<ticker>")
        return None

    # Train/val split (simple holdout)
    n = int(len(X_win))
    split = int(max(1, np.floor(0.85 * n)))
    X_tr, y_tr = X_win[:split], y_win[:split]
    X_va, y_va = X_win[split:], y_win[split:]

    # Build model: trunk + two quantile heads
    inp = keras.Input(shape=(int(lookback), int(X_win.shape[2])), name="x")
    x = keras.layers.LSTM(int(lstm_units), return_sequences=False, name="lstm")(inp)
    if float(dropout) > 0:
        x = keras.layers.Dropout(float(dropout), name="dropout")(x)
    x = keras.layers.Dense(int(dense_units), activation="relu", name="dense")(x)

    out_lo = keras.layers.Dense(1, name="q_lo")(x)
    out_hi = keras.layers.Dense(1, name="q_hi")(x)

    model = keras.Model(inputs=inp, outputs=[out_lo, out_hi], name="lstm_quantiles")

    opt = keras.optimizers.Adam(learning_rate=float(learning_rate))
    model.compile(
        optimizer=opt,
        loss={"q_lo": _pinball_loss(q_lo), "q_hi": _pinball_loss(q_hi)},
    )

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=10,
            restore_best_weights=True,
        )
    ]

    # Pylance fix: keras stubs can type verbose as str; cast through Any to preserve runtime.
    model_any = cast(Any, model)

    try:
        validation_data: Any
        if len(X_va) > 0:
            validation_data = (X_va, {"q_lo": y_va, "q_hi": y_va})
        else:
            validation_data = None

        model_any.fit(
            X_tr,
            {"q_lo": y_tr, "q_hi": y_tr},
            validation_data=validation_data,
            epochs=int(epochs),
            batch_size=int(batch_size),
            verbose=int(verbose),
            callbacks=callbacks,
        )
    except Exception as e:
        log.warning("LSTM: training failed for %s: %s", ticker or "<ticker>", e, exc_info=True)
        return None

    # Future index: avoid pd.Timestamp(Index) patterns (Pylance + runtime safety)
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, X_df.index.max())))
    fut_idx = _future_index(last_dt, int(fh_i))

    # Prepare future exog (if exog used in training)
    ex_future_aligned: Optional[pd.DataFrame] = None
    if ex_train_aligned is not None and not ex_train_aligned.empty:
        exf: Optional[pd.DataFrame] = None
        if exog_future is not None and not exog_future.empty:
            tmp = exog_future.copy()
            if not isinstance(tmp.index, pd.DatetimeIndex):
                tmp.index = pd.to_datetime(tmp.index, errors="coerce")
            tmp = cast(pd.DataFrame, tmp.sort_index())
            tmp = cast(pd.DataFrame, tmp.apply(pd.to_numeric, errors="coerce"))
            tmp = cast(pd.DataFrame, tmp.dropna(axis=1, how="all"))
            if not tmp.empty:
                tmp = cast(pd.DataFrame, tmp.reindex(index=fut_idx).ffill())
                exf = tmp

        if exf is None:
            last_row = cast(pd.Series, ex_train_aligned.iloc[-1])
            exf = pd.DataFrame([last_row.values] * int(fh_i), index=fut_idx, columns=ex_train_aligned.columns)

        ex_future_aligned = cast(pd.DataFrame, exf.reindex(index=fut_idx).ffill())
        if ex_future_aligned.isna().any(axis=None):
            last_row = cast(pd.Series, ex_train_aligned.iloc[-1])
            ex_future_aligned = pd.DataFrame([last_row.values] * int(fh_i), index=fut_idx, columns=ex_train_aligned.columns)

    # Recursive forecast (raw space feedback, scaled input window)
    last_hist_raw = X_raw[-int(lookback) :, :].copy()  # (lookback, n_features)
    preds: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []

    for step in range(int(fh_i)):
        X_in_raw = last_hist_raw.copy()
        X_in_scaled = _scale_minmax_apply(X_in_raw, x_min=x_min, x_range=x_range)
        X_in_scaled_3d = X_in_scaled.reshape(1, int(lookback), int(X_in_scaled.shape[1]))

        # Pylance fix: keras stubs may type verbose as str; cast through Any.
        try:
            qlo_hat, qhi_hat = model_any.predict(X_in_scaled_3d, verbose=0)
        except Exception as e:
            log.warning(
                "LSTM: predict failed for %s at step %d: %s",
                ticker or "<ticker>",
                step + 1,
                e,
                exc_info=True,
            )
            return None

        y_lo = float(np.asarray(qlo_hat).reshape(-1)[0])
        y_hi = float(np.asarray(qhi_hat).reshape(-1)[0])
        y_pred = 0.5 * (y_lo + y_hi)

        lowers.append(y_lo)
        uppers.append(y_hi)
        preds.append(y_pred)

        # Next raw row (target + exog)
        next_row = np.zeros((int(X_raw.shape[1]),), dtype=float)
        next_row[0] = y_pred

        if ex_future_aligned is not None and not ex_future_aligned.empty:
            ex_vals = ex_future_aligned.iloc[int(step)].to_numpy(dtype=float)
            next_row[1 : 1 + len(ex_vals)] = ex_vals

        last_hist_raw = np.vstack([last_hist_raw[1:, :], next_row])

    out_df = pd.DataFrame(
        {"LSTM_Pred": preds, "LSTM_Lower": lowers, "LSTM_Upper": uppers},
        index=fut_idx,
    )

    meta: Dict[str, Any] = {
        "ticker": ticker,
        "target_col": tgt,
        "fh": int(fh_i),
        "lookback": int(lookback),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "lstm_units": int(lstm_units),
        "dense_units": int(dense_units),
        "dropout": float(dropout),
        "learning_rate": float(learning_rate),
        "quantiles": (q_lo, q_hi),
        "n_features": int(X_raw.shape[1]),
        "n_samples": int(len(X_df)),
        "has_exog": bool(ex_train_aligned is not None),
    }

    return LSTMResult(
        model_used="LSTM-Quantile",
        cols_used=tuple(feat_cols),
        pred_df=out_df,
        meta=meta,
    )


__all__ = ["LSTMResult", "predict_lstm_quantiles"]
