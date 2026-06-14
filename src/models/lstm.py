# ------------------------
# src/models/lstm.py
# ------------------------

from __future__ import annotations

import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from src.models.intervals import discover_pi_settings, residual_quantile_expansion
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


def _discover_num(name: str, default: Any) -> Any:
    try:
        import Constants as C  # type: ignore

        return getattr(C, name, default)
    except Exception:
        return default


def _discover_str(name: str, default: str) -> str:
    """String constant discovery, with an environment-variable override.

    Precedence: ``os.environ[name]`` > ``Constants.<name>`` > ``default``. The env
    override keeps ad-hoc A/B runs (e.g. the Epic 3 returns-space toggle) ergonomic
    without editing ``compat/Constants.py``.
    """
    env = os.environ.get(name)
    if env is not None and str(env).strip() != "":
        return str(env)
    try:
        import Constants as C  # type: ignore

        return str(getattr(C, name, default))
    except Exception:
        return default


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
    return cast(
        pd.DatetimeIndex,
        pd.date_range(start=last_dt + to_offset("B"), periods=int(fh), freq="B"),
    )


# ----------------------------------------------------------------------
# Loss + dataset utilities
# ----------------------------------------------------------------------


def _pinball_loss(y_true: Any, y_pred: Any, q: float, torch_mod: Any) -> Any:
    qf = float(q)
    e = y_true - y_pred
    return torch_mod.mean(torch_mod.maximum(qf * e, (qf - 1.0) * e))


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


def _scale_minmax_apply(
    X: np.ndarray, x_min: np.ndarray, x_range: np.ndarray
) -> np.ndarray:
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
    quantiles: Optional[Tuple[float, float]] = None,
    train_window: Optional[int] = None,
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
    Quantile LSTM forecaster (PyTorch backend).

    Output
    ------
    DataFrame indexed by future business dates with columns:
      - LSTM_Pred  (directly-optimized median head, q=0.5, + OOS bias correction)
      - LSTM_Lower (q_lo, expanded if needed to contain LSTM_Pred)
      - LSTM_Upper (q_hi, expanded if needed to contain LSTM_Pred)

    Notes
    -----
    - PyTorch is optional. If missing, returns None.
    - Exogenous regressors are optional. If provided, they are concatenated as extra features.
    - Forecast is recursive: predicted point estimate feeds into the next step.
    - Target space (Epic 3) is configurable via ``LSTM_TARGET_SPACE`` (Constants or env):
      ``"level"`` (default) models price levels with min-max scaling; ``"returns"`` models
      next-step log-returns with z-score scaling and reconstructs the price path by
      compounding off the last observed price. In returns mode the interval radius is
      scaled by ``sqrt(horizon)`` (random-walk variance growth) and ``LSTM_RET_PI_WIDTH_MULT``
      replaces the level-mode ``LSTM_PI_WIDTH_MULT`` shrink.
    """
    if not getattr(cap, "HAS_TORCH", False):
        log.info("LSTM disabled: optional dependency 'torch' not available.")
        return None

    # Lazy torch import (keeps module import-safe)
    try:
        import torch  # type: ignore
        from torch import nn  # type: ignore
    except Exception as e:
        log.warning("LSTM disabled: could not import torch: %s", e)
        return None

    if enriched_data is None or enriched_data.empty:
        return None

    tgt = str(target_col) if target_col else _discover_target_col()
    fh_i = int(fh) if fh is not None else _discover_fh()
    fh_i = fh_i if fh_i > 0 else DEFAULT_FH

    pi = discover_pi_settings()
    lstm_pi_width_mult = float(_discover_num("LSTM_PI_WIDTH_MULT", 1.0))
    lstm_pi_width_mult = min(2.0, max(0.05, lstm_pi_width_mult))
    # Returns-mode interval width control (Epic 3). Default 1.0 = no shrink: the return
    # quantile heads + horizon-scaled conformal qhat define the band. Lower it to tighten
    # toward the nominal coverage target if the band runs conservative.
    lstm_ret_pi_width_mult = float(_discover_num("LSTM_RET_PI_WIDTH_MULT", 1.0))
    lstm_ret_pi_width_mult = min(2.0, max(0.05, lstm_ret_pi_width_mult))
    lstm_scaled_clip = float(_discover_num("LSTM_SCALED_CLIP", 0.20))
    if not np.isfinite(lstm_scaled_clip) or lstm_scaled_clip < 0.0:
        lstm_scaled_clip = 0.20
    if quantiles is None:
        q_lo, q_hi = float(pi.q_low), float(pi.q_high)
    else:
        q_lo, q_hi = float(quantiles[0]), float(quantiles[1])

    if not (0.0 < q_lo < q_hi < 1.0):
        raise ValueError("quantiles must satisfy 0 < q_lo < q_hi < 1.")

    if tgt not in enriched_data.columns:
        log.warning(
            "LSTM: target column '%s' missing for %s.", tgt, ticker or "<ticker>"
        )
        return None

    # Determinism (best effort)
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))

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

    train_window_i = int(train_window) if train_window is not None else 0
    if train_window_i > 0 and len(X_df) > train_window_i:
        X_df_recent = cast(pd.DataFrame, X_df.iloc[-train_window_i:].copy())
        if len(X_df_recent) >= min_need:
            X_df = X_df_recent
            y_ser = cast(pd.Series, X_df[tgt])
        else:
            log.warning(
                "LSTM: train_window=%d too short after alignment (%d rows, need >= %d). Using full history.",
                train_window_i,
                len(X_df_recent),
                min_need,
            )

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

    # Epic 3: target space is configurable. "returns" models next-step log-returns with
    # z-score scaling and reconstructs price by compounding; "level" (default) is the
    # Epic 2 price-level path. Set via Constants.LSTM_TARGET_SPACE or the env override.
    returns_mode = _discover_str("LSTM_TARGET_SPACE", "level").strip().lower() == "returns"
    ret_clip = float(_discover_num("LSTM_RET_CLIP", 0.25))  # raw |log-return| cap
    if not np.isfinite(ret_clip) or ret_clip <= 0.0:
        ret_clip = 0.25

    # Level-space scaler stats (kept defined in both modes for meta/back-compat).
    y_min = float(np.nanmin(y_raw))
    y_max = float(np.nanmax(y_raw))
    y_range = float(y_max - y_min)
    if not np.isfinite(y_range) or y_range <= 0.0:
        y_range = 1.0

    # Defaults so both branches leave every downstream name defined.
    x_min = x_range = None  # type: ignore[assignment]
    z_mu = z_sd = None  # type: ignore[assignment]
    recon_p0 = float("nan")

    if returns_mode:
        # Target channel -> next-step log-returns; z-score the whole feature matrix so
        # there is no [y_min, y_max] band for the recursion to revert toward.
        px = X_raw[:, 0].astype(float)
        if px.size < 2 or np.any(px <= 0.0) or not np.all(np.isfinite(px)):
            log.warning(
                "LSTM returns-mode: non-positive/short price series for %s; cannot transform.",
                ticker or "<ticker>",
            )
            return None
        ret0 = np.diff(np.log(px))  # len n-1
        X_ret = X_raw[1:, :].copy()
        X_ret[:, 0] = ret0
        recursion_src = X_ret
        recon_p0 = float(px[-1])
        z_mu = np.nanmean(X_ret, axis=0)
        z_sd = np.nanstd(X_ret, axis=0)
        z_sd[z_sd == 0.0] = 1.0
        X_scaled = (X_ret - z_mu) / z_sd
        y_scaled = (ret0 - float(z_mu[0])) / float(z_sd[0])
        y_scale_factor = float(z_sd[0])  # scaled residual -> raw return units
    else:
        # Scale target for stable quantile training on price-level series.
        recursion_src = X_raw
        y_scaled = (y_raw - y_min) / y_range
        X_scaled, x_min, x_range = _scale_minmax_fit(X_raw)
        y_scale_factor = y_range

    # Supervised windows
    X_win, y_win = _build_supervised_windows(X_scaled, y_scaled, lookback=int(lookback))
    if X_win.size == 0 or y_win.size == 0:
        log.warning(
            "LSTM: could not build supervised windows for %s.", ticker or "<ticker>"
        )
        return None

    # Train/val split (simple holdout)
    n = int(len(X_win))
    split = int(max(1, np.floor(0.85 * n)))
    X_tr, y_tr = X_win[:split], y_win[:split]
    X_va, y_va = X_win[split:], y_win[split:]

    n_features = int(X_win.shape[2])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    class _LSTMQuantileNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=n_features,
                hidden_size=int(lstm_units),
                num_layers=1,
                batch_first=True,
            )
            self.dropout = (
                nn.Dropout(float(dropout)) if float(dropout) > 0 else nn.Identity()
            )
            self.dense = nn.Linear(int(lstm_units), int(dense_units))
            self.relu = nn.ReLU()
            self.q_lo = nn.Linear(int(dense_units), 1)
            self.q_med = nn.Linear(int(dense_units), 1)
            self.q_hi = nn.Linear(int(dense_units), 1)

        def forward(self, x: Any) -> Tuple[Any, Any, Any]:
            out, _ = self.lstm(x)
            h = out[:, -1, :]
            h = self.dropout(h)
            h = self.relu(self.dense(h))
            return self.q_lo(h), self.q_med(h), self.q_hi(h)

    model = _LSTMQuantileNet().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))

    x_tr_t = torch.tensor(X_tr, dtype=torch.float32, device=device)
    y_tr_t = torch.tensor(y_tr, dtype=torch.float32, device=device)

    has_val = len(X_va) > 0
    if has_val:
        x_va_t = torch.tensor(X_va, dtype=torch.float32, device=device)
        y_va_t = torch.tensor(y_va, dtype=torch.float32, device=device)
    else:
        x_va_t = None
        y_va_t = None

    best_state: Optional[Dict[str, Any]] = None
    best_loss = float("inf")
    patience = 10
    bad_epochs = 0
    bs = max(1, int(batch_size))

    try:
        for ep in range(int(epochs)):
            model.train()
            perm = torch.randperm(x_tr_t.size(0), device=device)
            train_loss_acc = 0.0
            n_batches = 0

            for start in range(0, int(x_tr_t.size(0)), bs):
                idx = perm[start : start + bs]
                xb = x_tr_t.index_select(0, idx)
                yb = y_tr_t.index_select(0, idx)

                optimizer.zero_grad()
                lo_hat, med_hat, hi_hat = model(xb)
                loss = (
                    _pinball_loss(yb, lo_hat, q_lo, torch)
                    + _pinball_loss(yb, med_hat, 0.5, torch)
                    + _pinball_loss(yb, hi_hat, q_hi, torch)
                )
                loss.backward()
                optimizer.step()

                train_loss_acc += float(loss.detach().cpu().item())
                n_batches += 1

            train_loss = train_loss_acc / max(1, n_batches)

            if has_val and x_va_t is not None and y_va_t is not None:
                model.eval()
                with torch.no_grad():
                    lo_v, med_v, hi_v = model(x_va_t)
                    val_loss_t = (
                        _pinball_loss(y_va_t, lo_v, q_lo, torch)
                        + _pinball_loss(y_va_t, med_v, 0.5, torch)
                        + _pinball_loss(y_va_t, hi_v, q_hi, torch)
                    )
                    monitor = float(val_loss_t.detach().cpu().item())
            else:
                monitor = train_loss

            if monitor + 1e-9 < best_loss:
                best_loss = monitor
                best_state = deepcopy(model.state_dict())
                bad_epochs = 0
            else:
                bad_epochs += 1

            if int(verbose) > 0:
                if has_val:
                    log.info(
                        "LSTM[%s] epoch=%d train_loss=%.6f val_loss=%.6f",
                        ticker or "<ticker>",
                        ep + 1,
                        train_loss,
                        monitor,
                    )
                else:
                    log.info(
                        "LSTM[%s] epoch=%d train_loss=%.6f",
                        ticker or "<ticker>",
                        ep + 1,
                        train_loss,
                    )

            if bad_epochs >= patience:
                break

        if best_state is not None:
            model.load_state_dict(best_state)

    except Exception as e:
        log.warning(
            "LSTM: training failed for %s: %s", ticker or "<ticker>", e, exc_info=True
        )
        return None

    qhat = 0.0
    point_bias = 0.0
    calibration_split = "none"
    if bool(pi.calibration_enabled):
        try:
            # Out-of-sample calibration (Epic 2.3): residuals are taken on the
            # validation holdout and centered on the MEDIAN head, so neither the point
            # bias nor qhat is estimated in-sample. Fall back to train only when the
            # (replay) split produced no validation rows.
            if has_val and x_va_t is not None and y_va_t is not None:
                x_cal_t, y_cal_t = x_va_t, y_va_t
                calibration_split = "validation"
            else:
                x_cal_t, y_cal_t = x_tr_t, y_tr_t
                calibration_split = "train_fallback"

            model.eval()
            with torch.no_grad():
                _lo_cal, med_cal, _hi_cal = model(x_cal_t)

            med_np = med_cal.detach().cpu().numpy().reshape(-1)
            y_np = y_cal_t.detach().cpu().numpy().reshape(-1)
            resid_scaled = y_np - med_np  # signed; > 0 when the model under-predicts

            # qhat stays in SCALED space (it is subtracted/added to the scaled edges in
            # the recursion); point_bias maps to RAW price space (it shifts the raw
            # output band). Both are now out-of-sample and median-centered.
            qhat = residual_quantile_expansion(
                np.abs(resid_scaled),
                alpha=float(pi.alpha),
                min_samples=int(pi.calibration_min_samples),
            )
            point_bias = float(np.median(resid_scaled)) * float(y_scale_factor)
        except Exception:
            qhat = 0.0
            point_bias = 0.0

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
            exf = pd.DataFrame(
                [last_row.values] * int(fh_i),
                index=fut_idx,
                columns=ex_train_aligned.columns,
            )

        ex_future_aligned = cast(pd.DataFrame, exf.reindex(index=fut_idx).ffill())
        if ex_future_aligned.isna().any(axis=None):
            last_row = cast(pd.Series, ex_train_aligned.iloc[-1])
            ex_future_aligned = pd.DataFrame(
                [last_row.values] * int(fh_i),
                index=fut_idx,
                columns=ex_train_aligned.columns,
            )

    # Recursive forecast (raw space feedback, scaled input window)
    last_hist_raw = recursion_src[-int(lookback) :, :].copy()  # (lookback, n_features)
    p_prev = recon_p0  # running last price for returns-space reconstruction
    preds: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []

    model.eval()
    for step in range(int(fh_i)):
        X_in_raw = last_hist_raw.copy()
        if returns_mode:
            X_in_scaled = (X_in_raw - z_mu) / z_sd
        else:
            X_in_scaled = _scale_minmax_apply(X_in_raw, x_min=x_min, x_range=x_range)
        x_in = torch.tensor(
            X_in_scaled.reshape(1, int(lookback), int(X_in_scaled.shape[1])),
            dtype=torch.float32,
            device=device,
        )

        try:
            with torch.no_grad():
                qlo_hat, qmed_hat, qhi_hat = model(x_in)
        except Exception as e:
            log.warning(
                "LSTM: predict failed for %s at step %d: %s",
                ticker or "<ticker>",
                step + 1,
                e,
                exc_info=True,
            )
            return None

        y_lo_s = float(qlo_hat.detach().cpu().numpy().reshape(-1)[0])
        y_med_s = float(qmed_hat.detach().cpu().numpy().reshape(-1)[0])
        y_hi_s = float(qhi_hat.detach().cpu().numpy().reshape(-1)[0])
        if y_lo_s > y_hi_s:
            y_lo_s, y_hi_s = y_hi_s, y_lo_s

        if returns_mode:
            # Returns compound, so a one-step interval under-covers at longer horizons.
            # Scale the conformal radius by sqrt(step+1) (random-walk variance growth).
            # Do NOT apply lstm_pi_width_mult: the 0.30 shrink is a level-mode guardrail
            # for over-wide price heads; the return heads are already appropriately
            # scaled, and shrinking them collapses coverage (Epic 3 spike: 44% vs 86%).
            if qhat > 0.0 and np.isfinite(qhat):
                qhat_eff = float(qhat) * float(np.sqrt(step + 1))
                y_lo_s -= qhat_eff
                y_hi_s += qhat_eff
            if lstm_ret_pi_width_mult != 1.0:
                mid_s = 0.5 * (y_lo_s + y_hi_s)
                half_width_s = max(
                    0.0, 0.5 * (y_hi_s - y_lo_s) * float(lstm_ret_pi_width_mult)
                )
                y_lo_s = mid_s - half_width_s
                y_hi_s = mid_s + half_width_s
        else:
            if qhat > 0.0 and np.isfinite(qhat):
                y_lo_s -= float(qhat)
                y_hi_s += float(qhat)
            if lstm_pi_width_mult != 1.0:
                mid_s = 0.5 * (y_lo_s + y_hi_s)
                half_width_s = max(
                    0.0, 0.5 * (y_hi_s - y_lo_s) * float(lstm_pi_width_mult)
                )
                y_lo_s = mid_s - half_width_s
                y_hi_s = mid_s + half_width_s

        if returns_mode:
            # Returns space: inverse z-score to raw log-returns, de-bias the median,
            # cap |return| (replaces the [0,1] price-band clip), reconstruct price by
            # compounding off the running last price. exp() is monotone so ordered
            # returns yield ordered prices.
            r_lo = float(z_mu[0]) + y_lo_s * float(z_sd[0])
            r_med = float(z_mu[0]) + y_med_s * float(z_sd[0]) + float(point_bias)
            r_hi = float(z_mu[0]) + y_hi_s * float(z_sd[0])
            r_lo = float(np.clip(r_lo, -ret_clip, ret_clip))
            r_med = float(np.clip(r_med, -ret_clip, ret_clip))
            r_hi = float(np.clip(r_hi, -ret_clip, ret_clip))
            if r_lo > r_hi:
                r_lo, r_hi = r_hi, r_lo
            y_lo = p_prev * float(np.exp(r_lo))
            y_med = p_prev * float(np.exp(r_med))
            y_hi = p_prev * float(np.exp(r_hi))
            feedback_val = r_med
            p_prev = y_med
        else:
            # Guardrail: avoid runaway recursive collapse/explosion from unconstrained
            # heads. The median head (the point estimate) gets the same clip as the edges
            # but not qhat/width_mult, which are interval-shape ops, not point ops.
            clip_lo = -float(lstm_scaled_clip)
            clip_hi = 1.0 + float(lstm_scaled_clip)
            y_lo_s = float(np.clip(y_lo_s, clip_lo, clip_hi))
            y_med_s = float(np.clip(y_med_s, clip_lo, clip_hi))
            y_hi_s = float(np.clip(y_hi_s, clip_lo, clip_hi))
            if y_lo_s > y_hi_s:
                y_lo_s, y_hi_s = y_hi_s, y_lo_s

            # Raw price space. point_bias is a level correction applied to the whole
            # predictive band (preserves interval width).
            y_lo = y_min + y_lo_s * y_range + float(point_bias)
            y_med = y_min + y_med_s * y_range + float(point_bias)
            y_hi = y_min + y_hi_s * y_range + float(point_bias)
            feedback_val = float("nan")  # unused in level mode

        # Point = directly-optimized median head (Epic 2.2), replacing the old
        # midpoint-of-edges. Independent heads can cross under width_mult shrinkage, so
        # enforce Lower <= Pred <= Upper by expanding the edge to contain the point
        # (widen-only: never distorts the point estimate, never narrows coverage).
        y_pred = y_med
        y_lo = min(y_lo, y_pred)
        y_hi = max(y_hi, y_pred)

        lowers.append(y_lo)
        uppers.append(y_hi)
        preds.append(y_pred)

        # Next raw row (target + exog). Returns mode feeds the predicted return back into
        # the target channel; level mode feeds the predicted price.
        next_row = np.zeros((int(recursion_src.shape[1]),), dtype=float)
        next_row[0] = feedback_val if returns_mode else y_pred

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
        "train_window": int(train_window_i),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "lstm_units": int(lstm_units),
        "dense_units": int(dense_units),
        "dropout": float(dropout),
        "learning_rate": float(learning_rate),
        "quantiles": (q_lo, q_hi),
        "pi_coverage": float(pi.coverage),
        "pi_alpha": float(pi.alpha),
        "pi_q_low": float(pi.q_low),
        "pi_q_high": float(pi.q_high),
        "pi_calibration_enabled": bool(pi.calibration_enabled),
        "lstm_pi_width_mult": float(lstm_pi_width_mult),
        "lstm_scaled_clip": float(lstm_scaled_clip),
        "pi_qhat": float(qhat),
        "point_bias": float(point_bias),
        "calibration_split": calibration_split,
        "target_space": "log_returns" if returns_mode else "level",
        "ret_clip": float(ret_clip) if returns_mode else None,
        "lstm_ret_pi_width_mult": (
            float(lstm_ret_pi_width_mult) if returns_mode else None
        ),
        "n_features": int(X_raw.shape[1]),
        "n_samples": int(len(X_df)),
        "has_exog": bool(ex_train_aligned is not None),
        "backend": "torch",
        "device": str(device),
    }

    return LSTMResult(
        model_used="LSTM-Quantile-Torch",
        cols_used=tuple(feat_cols),
        pred_df=out_df,
        meta=meta,
    )


__all__ = ["LSTMResult", "predict_lstm_quantiles"]
