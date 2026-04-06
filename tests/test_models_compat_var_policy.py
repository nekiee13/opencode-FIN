from __future__ import annotations

from src.models.compat_api import _resolve_var_best_lag


def test_resolve_var_best_lag_defaults_to_one_for_zero_none_invalid() -> None:
    assert _resolve_var_best_lag(0, max_lags=10) == 1
    assert _resolve_var_best_lag(None, max_lags=10) == 1
    assert _resolve_var_best_lag("", max_lags=10) == 1
    assert _resolve_var_best_lag("nan", max_lags=10) == 1


def test_resolve_var_best_lag_respects_positive_values_and_caps_to_max() -> None:
    assert _resolve_var_best_lag(3, max_lags=10) == 3
    assert _resolve_var_best_lag("4", max_lags=10) == 4
    assert _resolve_var_best_lag(99, max_lags=10) == 10
