from __future__ import annotations

from src.ui.services.error_parse import classify_stage_error


def test_classify_stage_error_data_missing() -> None:
    code = classify_stage_error(
        returncode=1,
        stderr="RuntimeError: no data available after applying history mode",
        stdout="",
    )
    assert code == "DATA_MISSING"


def test_classify_stage_error_argument_error() -> None:
    code = classify_stage_error(
        returncode=2,
        stderr="--as-of-date is required when --history-mode replay is used.",
        stdout="",
    )
    assert code == "ARGUMENT_ERROR"


def test_classify_stage_error_ok() -> None:
    code = classify_stage_error(returncode=0, stderr="", stdout="done")
    assert code == "NONE"
