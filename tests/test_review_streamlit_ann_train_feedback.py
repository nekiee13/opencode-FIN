from __future__ import annotations

from src.ui.review_streamlit import (
    _normalize_ann_signal_rows,
    _parse_ann_train_stdout_tables,
    _summarize_ann_training_health,
    _target_modes_from_selection,
)


def test_target_modes_from_selection_supports_all() -> None:
    assert _target_modes_from_selection("all") == ["magnitude", "sgn"]
    assert _target_modes_from_selection("sgn") == ["sgn"]
    assert _target_modes_from_selection("magnitude") == ["magnitude"]


def test_summarize_ann_training_health_reports_unsuccessful_statuses() -> None:
    payload = {
        "tickers": {
            "TNX": {
                "tune_matrix": {
                    "magnitude": {"status": "fails_baseline"},
                    "sgn": {"status": "healthy"},
                }
            },
            "DJI": {
                "tune_matrix": {
                    "magnitude": {"status": "healthy"},
                    "sgn": {"status": "insufficient_data"},
                }
            },
        }
    }

    level, text = _summarize_ann_training_health(
        payload,
        target_modes=["magnitude", "sgn"],
    )

    assert level == "error"
    assert "fails_baseline" in text
    assert "insufficient_data" in text


def test_summarize_ann_training_health_reports_success_when_all_healthy() -> None:
    payload = {
        "tickers": {
            "TNX": {
                "tune_matrix": {
                    "magnitude": {"status": "healthy"},
                    "sgn": {"status": "healthy"},
                }
            }
        }
    }

    level, text = _summarize_ann_training_health(
        payload,
        target_modes=["magnitude", "sgn"],
    )

    assert level == "success"
    assert "completed successfully" in text


def test_parse_ann_train_stdout_tables_parses_summary_and_features() -> None:
    stdout = (
        "[mode=sgn] "
        "[ann_train] run_dir=/tmp/run_sgn "
        "[ann_train] rows=48 "
        "[ann_train] features=230/230 "
        "[ann_train] r2=0.999993 "
        "[ann_train] top_feature #1 ti::RSI__lag0 score=0.33 "
        "[ann_train] top_feature #2 ti::ROC__lag0 score=0.27"
    )

    summary_rows, feature_rows = _parse_ann_train_stdout_tables(stdout)

    assert len(summary_rows) == 1
    assert summary_rows[0]["Mode"] == "sgn"
    assert summary_rows[0]["Rows"] == "48"
    assert summary_rows[0]["Features"] == "230/230"
    assert summary_rows[0]["R2"] == "0.999993"

    assert len(feature_rows) == 2
    assert feature_rows[0]["Mode"] == "sgn"
    assert feature_rows[0]["Rank"] == "1"
    assert feature_rows[0]["Feature"] == "ti::RSI__lag0"
    assert feature_rows[0]["Score"] == "0.33"


def test_normalize_ann_signal_rows_maps_sgn_symbols_for_display() -> None:
    rows = [
        {"Ticker": "TNX", "SGN": "+", "Magnitude": "0.1000"},
        {"Ticker": "DJI", "SGN": "-", "Magnitude": "0.2000"},
        {"Ticker": "SPX", "SGN": "", "Magnitude": ""},
    ]

    out = _normalize_ann_signal_rows(rows)

    assert out[0]["SGN"] == "+1"
    assert out[1]["SGN"] == "-1"
    assert out[2]["SGN"] == "N/A"
