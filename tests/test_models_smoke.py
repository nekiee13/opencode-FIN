# ------------------------
# tests/test_models_smoke.py
# ------------------------
"""
Model smoke tests for FIN.

Goals
-----
- Fast, deterministic smoke coverage for core model entrypoints.
- Graceful behavior when optional dependencies are missing (skip).
- Output schema verification (FH rows, DatetimeIndex, expected columns) when models run.

Run
---
pytest -q

Notes
-----
- Assertions are structural (shape/schema/index), not accuracy-focused.
- If a model is dependency-gated (TensorFlow, statsmodels, chaospy, scikit-learn),
  the corresponding test is skipped when the dependency is unavailable.
"""

from __future__ import annotations

import importlib
from typing import Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _ts(x: object) -> pd.Timestamp:
    """
    Coerce an arbitrary object into a pandas Timestamp.

    Rationale
    ---------
    Pandas typing in editors sometimes widens index scalar types to Index[Any].
    This helper both coerces and narrows typing via cast to satisfy type checkers.
    """
    return cast(pd.Timestamp, pd.to_datetime(x))


def _make_bday_ohlcv(
    n: int = 260,
    *,
    start: str = "2024-01-02",
    seed: int = 123,
) -> pd.DataFrame:
    """
    Produce a business-day OHLCV DataFrame with mild trending Close and noise.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n)

    noise = rng.normal(0.0, 0.5, size=n).cumsum()
    base = 100.0 + np.linspace(0.0, 5.0, n) + noise
    close = np.maximum(base, 1.0)

    open_ = close + rng.normal(0.0, 0.2, size=n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0.2, 0.1, size=n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.2, 0.1, size=n))
    vol = rng.integers(1_000_000, 2_000_000, size=n)

    return pd.DataFrame(
        {
            "Open": open_.astype(float),
            "High": high.astype(float),
            "Low": low.astype(float),
            "Close": close.astype(float),
            "Volume": vol.astype(float),
        },
        index=idx,
    )


def _future_bdays(last_dt: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return pd.bdate_range(last_dt + pd.tseries.frequencies.to_offset("B"), periods=fh, freq="B")


def _has_module(modname: str) -> bool:
    try:
        importlib.import_module(modname)
        return True
    except Exception:
        return False


def _has_fin_compat_flag(flag_name: str) -> Optional[bool]:
    """
    Return FIN compat boolean if src.utils.compat exists; otherwise None.
    """
    try:
        compat = importlib.import_module("src.utils.compat")
        v = getattr(compat, flag_name, None)
        return bool(v) if v is not None else None
    except Exception:
        return None


def _assert_forecast_df(
    df: pd.DataFrame,
    *,
    fh: int,
    cols: Sequence[str],
    last_dt: pd.Timestamp,
) -> None:
    assert df is not None
    assert isinstance(df, pd.DataFrame)
    assert len(df) == fh
    assert isinstance(df.index, pd.DatetimeIndex)

    exp_idx = _future_bdays(last_dt, fh)
    assert df.index.equals(exp_idx)

    for c in cols:
        assert c in df.columns

    # Must be numeric or NaN; allow intervals to be NaN when disabled.
    for c in cols:
        assert pd.api.types.is_numeric_dtype(df[c]) or df[c].isna().all()


# ---------------------------------------------------------------------
# Random Walk
# ---------------------------------------------------------------------


def test_random_walk_smoke_fh3() -> None:
    from src.models.random_walk import predict_random_walk

    df = _make_bday_ohlcv(n=120)
    fh = 3
    out = predict_random_walk(df, ticker="TEST", fh=fh)

    assert out is not None
    _assert_forecast_df(
        out,
        fh=fh,
        cols=("RW_Pred", "RW_Lower", "RW_Upper"),
        last_dt=_ts(df.index[-1]),
    )


# ---------------------------------------------------------------------
# VAR (statsmodels optional)
# ---------------------------------------------------------------------


def test_var_smoke_skips_if_missing_statsmodels() -> None:
    has_flag = _has_fin_compat_flag("HAS_STATSMODELS")
    has_statsmodels = bool(has_flag) if has_flag is not None else _has_module("statsmodels")
    if not has_statsmodels:
        pytest.skip("statsmodels not available; VAR smoke test skipped.")

    from src.models.var import predict_var

    df = _make_bday_ohlcv(n=260)
    fh = 3
    out = predict_var(df, ticker="TEST", fh=fh)

    assert out is not None
    _assert_forecast_df(
        out,
        fh=fh,
        cols=("VAR_Pred", "VAR_Lower", "VAR_Upper"),
        last_dt=_ts(df.index[-1]),
    )


# ---------------------------------------------------------------------
# PCE-NARX (chaospy + scikit-learn optional)
# ---------------------------------------------------------------------


def test_pce_narx_smoke_skips_if_missing_deps() -> None:
    has_chaospy = _has_module("chaospy")
    has_sklearn = _has_module("sklearn")
    if not (has_chaospy and has_sklearn):
        pytest.skip("chaospy and/or scikit-learn not available; PCE-NARX smoke test skipped.")

    from src.models.pce_narx import predict_pce_narx

    df = _make_bday_ohlcv(n=260)
    fh = 3

    out = predict_pce_narx(df, ticker="TEST", fh=fh)

    assert out is not None
    _assert_forecast_df(
        out,
        fh=fh,
        cols=("PCE_Pred", "PCE_Lower", "PCE_Upper"),
        last_dt=_ts(df.index[-1]),
    )


# ---------------------------------------------------------------------
# LSTM Quantiles (tensorflow optional)
# ---------------------------------------------------------------------


def test_lstm_quantiles_smoke_skips_if_missing_tensorflow() -> None:
    has_flag = _has_fin_compat_flag("HAS_TENSORFLOW")
    has_tf = bool(has_flag) if has_flag is not None else _has_module("tensorflow")
    if not has_tf:
        pytest.skip("tensorflow not available; LSTM smoke test skipped.")

    from src.models.lstm import predict_lstm_quantiles

    df = _make_bday_ohlcv(n=320)
    fh = 3

    res = predict_lstm_quantiles(
        df,
        ticker="TEST",
        fh=fh,
        lookback=30,
        epochs=2,
        batch_size=32,
        lstm_units=16,
        dense_units=8,
        dropout=0.0,
        verbose=0,
        min_samples=120,
        seed=7,
    )

    assert res is not None
    assert res.pred_df is not None

    # Model internally uses business-day regularization; mirror that here for expected last_dt.
    df_b = cast(pd.DataFrame, df.asfreq("B").ffill())
    _assert_forecast_df(
        res.pred_df,
        fh=fh,
        cols=("LSTM_Pred", "LSTM_Lower", "LSTM_Upper"),
        last_dt=_ts(df_b.index[-1]),
    )
    assert isinstance(res.cols_used, tuple)
    assert "Close" in res.cols_used


# ---------------------------------------------------------------------
# Package-level: import smoke for model modules
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "modname, deps",
    [
        ("src.models.random_walk", ()),
        ("src.models.var", ("statsmodels",)),
        ("src.models.pce_narx", ("chaospy", "sklearn")),
        ("src.models.lstm", ("tensorflow",)),
    ],
)
def test_model_module_imports(modname: str, deps: Tuple[str, ...]) -> None:
    for d in deps:
        if not _has_module(d):
            pytest.skip(f"{d} missing; import test skipped for {modname}.")
    mod = importlib.import_module(modname)
    assert mod is not None
