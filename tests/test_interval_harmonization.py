from __future__ import annotations

import types
from typing import Any, Dict

import numpy as np
import pandas as pd


def test_discover_pi_settings_defaults() -> None:
    from src.models.intervals import discover_pi_settings

    pi = discover_pi_settings()
    assert abs(pi.coverage - 0.90) < 1e-9
    assert abs(pi.alpha - 0.10) < 1e-9
    assert abs(pi.q_low - 0.05) < 1e-9
    assert abs(pi.q_high - 0.95) < 1e-9
    assert pi.z_two_sided > 1.6 and pi.z_two_sided < 2.0


def test_residual_quantile_expansion_basic() -> None:
    from src.models.intervals import residual_quantile_expansion

    resid = np.array([-1.0, -0.5, 0.25, 0.75, 2.0], dtype=float)
    qhat = residual_quantile_expansion(resid, alpha=0.10, min_samples=3)
    assert qhat >= 0.75


def test_compat_lstm_uses_harmonized_quantiles(monkeypatch) -> None:
    import src.models.compat_api as compat_api

    idx = pd.bdate_range("2025-01-02", periods=300, freq="B")
    df = pd.DataFrame({"Close": np.linspace(100.0, 120.0, len(idx))}, index=idx)

    captured: Dict[str, Any] = {}

    def _fake_predict_lstm_quantiles(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["quantiles"] = kwargs.get("quantiles")
        captured["train_window"] = kwargs.get("train_window")
        out_idx = pd.bdate_range(idx[-1] + pd.offsets.BDay(1), periods=3, freq="B")
        out_df = pd.DataFrame(
            {
                "LSTM_Pred": [1.0, 1.1, 1.2],
                "LSTM_Lower": [0.9, 1.0, 1.1],
                "LSTM_Upper": [1.1, 1.2, 1.3],
            },
            index=out_idx,
        )
        return types.SimpleNamespace(pred_df=out_df)

    import src.models.lstm as lstm_mod

    monkeypatch.setattr(
        lstm_mod, "predict_lstm_quantiles", _fake_predict_lstm_quantiles
    )

    out = compat_api.predict_lstm(df, ticker="TEST", exo_config=None)
    assert out is not None
    assert captured["quantiles"] == (0.05, 0.95)
    assert int(captured["train_window"]) == 450


def test_compat_arima_pmdarima_uses_harmonized_alpha(monkeypatch) -> None:
    import src.models.compat_api as compat_api

    idx = pd.bdate_range("2024-01-02", periods=260, freq="B")
    df = pd.DataFrame({"Close": np.linspace(100.0, 130.0, len(idx))}, index=idx)

    captured: Dict[str, Any] = {}

    class _FakeModel:
        order = (1, 1, 1)

        def predict(self, n_periods, X=None, return_conf_int=False, alpha=None):  # type: ignore[no-untyped-def]
            captured["alpha"] = alpha
            preds = np.full(int(n_periods), 111.0, dtype=float)
            ci = np.column_stack([preds - 1.0, preds + 1.0])
            return preds, ci

        def resid(self):  # type: ignore[no-untyped-def]
            return np.array([0.1, -0.2, 0.3, -0.1, 0.05], dtype=float)

    class _FakePM:
        @staticmethod
        def auto_arima(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _FakeModel()

    import sys

    monkeypatch.setitem(sys.modules, "pmdarima", _FakePM())

    out_df, order, resid = compat_api.predict_arima(df, ticker="TEST", exo_config=None)

    assert out_df is not None
    assert order == (1, 1, 1)
    assert resid is not None
    assert abs(float(captured["alpha"]) - 0.10) < 1e-9
