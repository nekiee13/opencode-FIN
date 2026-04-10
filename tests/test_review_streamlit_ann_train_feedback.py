from __future__ import annotations

from src.ui.review_streamlit import (
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
