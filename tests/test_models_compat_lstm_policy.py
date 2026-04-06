from __future__ import annotations

from src.models.compat_api import _select_lstm_training_policy


def test_select_lstm_training_policy_keeps_default_for_live_mode() -> None:
    lookback, min_samples = _select_lstm_training_policy(
        history_mode="live",
        available_rows=56,
        configured_lookback=60,
    )
    assert lookback == 60
    assert min_samples == 120


def test_select_lstm_training_policy_relaxes_for_replay_low_history() -> None:
    lookback, min_samples = _select_lstm_training_policy(
        history_mode="replay",
        available_rows=56,
        configured_lookback=60,
    )
    assert lookback == 20
    assert min_samples == 45


def test_select_lstm_training_policy_replay_uses_full_when_sufficient_rows() -> None:
    lookback, min_samples = _select_lstm_training_policy(
        history_mode="replay",
        available_rows=180,
        configured_lookback=60,
    )
    assert lookback == 60
    assert min_samples == 120
