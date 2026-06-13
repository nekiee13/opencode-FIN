# ------------------------
# tests/test_lstm_backtest.py
# ------------------------
"""
Tests for the LSTM backtest harness (tools/lstm_backtest.py).

These verify the *measurement* itself — metric math, the leakage guard, skip
accounting, and determinism of aggregates — NOT the LSTM model. The model entry
point (``predict_lstm``) and the data loader (``fetch_data``) are monkeypatched,
so the tests need neither real ticker CSVs nor torch. They exercise pure harness
logic and are fast and hermetic.

numpy/pandas are mandatory project dependencies, so importing the harness is
expected to succeed in any configured environment.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import tools.lstm_backtest as bt


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _cfg(**overrides) -> bt.BacktestConfig:
    base = dict(
        tickers=["X"],
        start=None,
        end=None,
        step=5,
        fh=3,
        history_mode="replay",
        seed=42,
        out_dir=Path("/tmp/lstm_bt_test"),
        skip_threshold=0.10,
    )
    base.update(overrides)
    return bt.BacktestConfig(**base)


def _hist_frame(last: str, n: int = 200) -> pd.DataFrame:
    """Synthetic OHLC-ish frame with a Close column and DatetimeIndex up to `last`."""
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    return pd.DataFrame({"Close": [100.0 + i * 0.1 for i in range(n)]}, index=idx)


def _forecast_frame(start_after: pd.Timestamp, preds, lowers, uppers) -> pd.DataFrame:
    idx = pd.bdate_range(start=start_after + pd.tseries.offsets.BDay(1), periods=len(preds))
    return pd.DataFrame(
        {"LSTM_Pred": preds, "LSTM_Lower": lowers, "LSTM_Upper": uppers}, index=idx
    )


# ----------------------------------------------------------------------
# _sign
# ----------------------------------------------------------------------
def test_sign() -> None:
    assert bt._sign(2.0) == 1
    assert bt._sign(-2.0) == -1
    assert bt._sign(0.0) == 0


# ----------------------------------------------------------------------
# _score_step — per-point metric formulas
# ----------------------------------------------------------------------
def test_score_step_known_values() -> None:
    cfg = _cfg()
    base = bt._row_template(cfg, "X", pd.Timestamp("2025-01-10"))
    row = bt._score_step(
        base,
        horizon_step=1,
        forecast_date=pd.Timestamp("2025-01-13"),
        last_close=100.0,
        pred=105.0,
        lower=95.0,
        upper=110.0,
        actual=102.0,
    )
    assert row["signed_err"] == pytest.approx(3.0)        # 105 - 102
    assert row["abs_err"] == pytest.approx(3.0)
    assert row["sq_err"] == pytest.approx(9.0)
    assert row["ape"] == pytest.approx(3.0 / 102.0)
    assert row["smape_term"] == pytest.approx(2.0 * 3.0 / (105.0 + 102.0))
    assert row["in_interval"] == 1                        # 95 <= 102 <= 110
    assert row["interval_width"] == pytest.approx(15.0)
    assert row["norm_width"] == pytest.approx(15.0 / 100.0)
    assert row["dir_pred"] == 1                           # 105 > 100
    assert row["dir_actual"] == 1                         # 102 > 100
    assert row["dir_eligible"] == 1
    assert row["dir_hit"] == 1
    assert row["status"] == "scored"


def test_score_step_direction_miss_and_outside_interval() -> None:
    cfg = _cfg()
    base = bt._row_template(cfg, "X", pd.Timestamp("2025-01-10"))
    row = bt._score_step(
        base,
        horizon_step=2,
        forecast_date=pd.Timestamp("2025-01-14"),
        last_close=100.0,
        pred=96.0,        # predicts down
        lower=90.0,
        upper=99.0,
        actual=103.0,     # actually up, and outside [90, 99]
    )
    assert row["dir_pred"] == -1
    assert row["dir_actual"] == 1
    assert row["dir_hit"] == 0
    assert row["in_interval"] == 0


def test_score_step_flat_actual_is_direction_ineligible() -> None:
    cfg = _cfg()
    base = bt._row_template(cfg, "X", pd.Timestamp("2025-01-10"))
    row = bt._score_step(
        base, horizon_step=1, forecast_date=pd.Timestamp("2025-01-13"),
        last_close=100.0, pred=101.0, lower=95.0, upper=105.0, actual=100.0,
    )
    assert row["dir_actual"] == 0
    assert row["dir_eligible"] == 0
    assert row["dir_hit"] is None


# ----------------------------------------------------------------------
# _metric_block — aggregate formulas
# ----------------------------------------------------------------------
def test_metric_block_known() -> None:
    cfg = _cfg()
    base = bt._row_template(cfg, "X", pd.Timestamp("2025-01-10"))
    r1 = bt._score_step(base, horizon_step=1, forecast_date=pd.Timestamp("2025-01-13"),
                        last_close=100.0, pred=104.0, lower=98.0, upper=110.0, actual=101.0)
    r2 = bt._score_step(base, horizon_step=2, forecast_date=pd.Timestamp("2025-01-14"),
                        last_close=100.0, pred=96.0, lower=90.0, upper=99.0, actual=103.0)
    block = bt._metric_block(pd.DataFrame([r1, r2]))

    assert block["N"] == 2
    assert block["MAE"] == pytest.approx(5.0)             # mean(3, 7)
    assert block["RMSE"] == pytest.approx(((9.0 + 49.0) / 2) ** 0.5)  # sqrt(29) ≈ 5.385
    assert block["MBE"] == pytest.approx(-2.0)            # mean(3, -7)
    assert block["MedAE"] == pytest.approx(5.0)
    assert block["coverage_pct"] == pytest.approx(50.0)   # 1 of 2 inside
    assert block["dir_hit_rate"] == pytest.approx(50.0)   # r1 hit, r2 miss


def test_metric_block_empty() -> None:
    assert bt._metric_block(pd.DataFrame([]))["N"] == 0


# ----------------------------------------------------------------------
# aggregate — skip accounting + threshold flag
# ----------------------------------------------------------------------
def test_aggregate_skip_accounting() -> None:
    cfg = _cfg(skip_threshold=0.10)
    as_of = pd.Timestamp("2025-01-10")
    base = bt._row_template(cfg, "X", as_of)
    scored1 = bt._score_step(base, horizon_step=1, forecast_date=pd.Timestamp("2025-01-13"),
                             last_close=100.0, pred=101.0, lower=98.0, upper=104.0, actual=101.0)
    scored2 = bt._score_step(base, horizon_step=2, forecast_date=pd.Timestamp("2025-01-14"),
                             last_close=100.0, pred=99.0, lower=96.0, upper=102.0, actual=98.0)
    skip_a = bt._skip_row(cfg, "X", as_of, "no_actual", horizon_step=3,
                          forecast_date=pd.Timestamp("2025-01-15"))
    skip_b = bt._skip_row(cfg, "X", as_of, "model_none")

    summary = bt.aggregate([scored1, scored2, skip_a, skip_b], cfg)
    ov = summary["overall"]
    assert ov["N_scored"] == 2
    assert ov["N_skipped"] == 2
    assert ov["skip_rate"] == pytest.approx(0.5)
    assert summary["skips"] == {"no_actual": 1, "model_none": 1}
    assert summary["skip_threshold_exceeded"] is True
    assert ov["coverage_target"] == bt.COVERAGE_TARGET
    # per-horizon present for the two scored steps
    steps = {b["horizon_step"] for b in summary["per_horizon"]}
    assert steps == {1, 2}


def test_aggregate_under_threshold_not_flagged() -> None:
    cfg = _cfg(skip_threshold=0.90)
    as_of = pd.Timestamp("2025-01-10")
    base = bt._row_template(cfg, "X", as_of)
    scored = bt._score_step(base, horizon_step=1, forecast_date=pd.Timestamp("2025-01-13"),
                            last_close=100.0, pred=101.0, lower=98.0, upper=104.0, actual=101.0)
    skip = bt._skip_row(cfg, "X", as_of, "no_actual")
    summary = bt.aggregate([scored, skip], cfg)
    assert summary["skip_threshold_exceeded"] is False


# ----------------------------------------------------------------------
# run_one — leakage guard, skip reasons, scoring (model mocked, no torch)
# ----------------------------------------------------------------------
def test_run_one_leakage_assert_is_caught(monkeypatch) -> None:
    """A training frame that post-dates as_of must trip the leakage assert."""
    as_of = pd.Timestamp("2025-03-10")
    # fetch_data returns rows AFTER as_of -> violates train_max <= as_of
    bad = _hist_frame("2025-04-01", n=50)
    monkeypatch.setattr(bt, "fetch_data", lambda *a, **k: bad)
    monkeypatch.setattr(bt, "predict_lstm", lambda *a, **k: None)

    rows = bt.run_one(_cfg(), "X", as_of, pd.Series(dtype=float))
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert rows[0]["skip_reason"].startswith("error:AssertionError")


def test_run_one_model_none(monkeypatch) -> None:
    as_of = pd.Timestamp("2025-03-10")
    monkeypatch.setattr(bt, "fetch_data", lambda *a, **k: _hist_frame("2025-03-10"))
    monkeypatch.setattr(bt, "predict_lstm", lambda *a, **k: None)

    rows = bt.run_one(_cfg(), "X", as_of, pd.Series(dtype=float))
    assert [r["skip_reason"] for r in rows] == ["model_none"]


def test_run_one_no_actual_when_forecast_date_missing(monkeypatch) -> None:
    as_of = pd.Timestamp("2025-03-10")
    hist = _hist_frame("2025-03-10")
    fc = _forecast_frame(as_of, preds=[101, 102, 103], lowers=[99, 99, 99], uppers=[104, 105, 106])
    monkeypatch.setattr(bt, "fetch_data", lambda *a, **k: hist)
    monkeypatch.setattr(bt, "predict_lstm", lambda *a, **k: fc)

    # Actuals empty -> every forecast date is "no_actual"
    rows = bt.run_one(_cfg(), "X", as_of, pd.Series(dtype=float))
    assert len(rows) == 3
    assert all(r["skip_reason"] == "no_actual" for r in rows)
    assert all(r["status"] == "skipped" for r in rows)


def test_run_one_scores_when_actuals_present(monkeypatch) -> None:
    as_of = pd.Timestamp("2025-03-10")
    hist = _hist_frame("2025-03-10")
    fc = _forecast_frame(as_of, preds=[101.0, 102.0, 103.0],
                         lowers=[99.0, 99.0, 99.0], uppers=[104.0, 105.0, 106.0])
    actuals = pd.Series([100.5, 101.5, 99.0], index=fc.index)  # realized closes
    monkeypatch.setattr(bt, "fetch_data", lambda *a, **k: hist)
    monkeypatch.setattr(bt, "predict_lstm", lambda *a, **k: fc)

    rows = bt.run_one(_cfg(), "X", as_of, actuals)
    assert len(rows) == 3
    assert all(r["status"] == "scored" for r in rows)
    # first step: pred 101.0 vs actual 100.5 -> signed_err 0.5
    assert rows[0]["signed_err"] == pytest.approx(0.5)
    assert rows[0]["horizon_step"] == 1


def test_run_one_nan_pred_skipped(monkeypatch) -> None:
    as_of = pd.Timestamp("2025-03-10")
    hist = _hist_frame("2025-03-10")
    fc = _forecast_frame(as_of, preds=[float("nan"), 102.0, 103.0],
                         lowers=[99.0, 99.0, 99.0], uppers=[104.0, 105.0, 106.0])
    actuals = pd.Series([100.5, 101.5, 99.0], index=fc.index)
    monkeypatch.setattr(bt, "fetch_data", lambda *a, **k: hist)
    monkeypatch.setattr(bt, "predict_lstm", lambda *a, **k: fc)

    rows = bt.run_one(_cfg(), "X", as_of, actuals)
    assert rows[0]["skip_reason"] == "nan_pred"
    assert rows[1]["status"] == "scored"


# ----------------------------------------------------------------------
# Determinism — metric aggregates are a pure function of the rows
# ----------------------------------------------------------------------
def test_aggregate_metrics_are_deterministic() -> None:
    cfg = _cfg()
    as_of = pd.Timestamp("2025-01-10")
    base = bt._row_template(cfg, "X", as_of)
    rows = [
        bt._score_step(base, horizon_step=1, forecast_date=pd.Timestamp("2025-01-13"),
                       last_close=100.0, pred=104.0, lower=98.0, upper=110.0, actual=101.0),
        bt._score_step(base, horizon_step=2, forecast_date=pd.Timestamp("2025-01-14"),
                       last_close=100.0, pred=96.0, lower=90.0, upper=99.0, actual=103.0),
    ]
    s1 = bt.aggregate(list(rows), cfg)
    s2 = bt.aggregate(list(rows), cfg)
    # Metric blocks are identical (run.timestamp intentionally differs).
    assert s1["overall"] == s2["overall"]
    assert s1["per_horizon"] == s2["per_horizon"]
    assert s1["per_ticker"] == s2["per_ticker"]


# ----------------------------------------------------------------------
# resolve_as_of_dates — default window derivation
# ----------------------------------------------------------------------
def test_resolve_as_of_dates_default_window() -> None:
    cfg = _cfg(start=None, end=None, step=5, fh=3)
    actuals = {"X": pd.Series([1.0] * 300, index=pd.bdate_range(end="2025-06-12", periods=300))}
    dates = bt.resolve_as_of_dates(cfg, actuals)
    assert len(dates) > 0
    # end is data_end - fh business days; all as-of dates fall on/before it.
    data_end = pd.Timestamp("2025-06-12")
    expected_end = data_end - pd.tseries.offsets.BDay(cfg.fh)
    assert max(dates) <= expected_end
    # stepping of 5 business days between consecutive as-of points
    if len(dates) >= 2:
        assert (dates[1] - dates[0]).days in (7, 5)  # 5 bdays spans a weekend (7 cal days)


def test_resolve_as_of_dates_empty_when_no_actuals() -> None:
    assert bt.resolve_as_of_dates(_cfg(), {}) == []
