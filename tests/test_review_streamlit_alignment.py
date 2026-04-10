from __future__ import annotations

from src.ui.review_streamlit import _global_right_align_css


def test_global_right_align_css_targets_headers_values_and_tables() -> None:
    css = _global_right_align_css()

    assert "text-align: right" in css
    assert "stDataFrame" in css
    assert "stDataFrameGlideDataEditor" in css
    assert "stTable" in css
    assert "stMetricValue" in css
    assert "stMetricLabel" in css
    assert "stSelectbox" in css
    assert "stNumberInput" in css


def test_global_right_align_css_has_pipeline_qa_left_override() -> None:
    css = _global_right_align_css()

    assert "pipeline-qa-left" in css
    assert "text-align: left" in css


def test_global_right_align_css_has_json_left_override() -> None:
    css = _global_right_align_css()

    assert "json-left" in css
    assert "text-align: left" in css
