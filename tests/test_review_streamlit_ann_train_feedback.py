from __future__ import annotations

from src.ui.review_streamlit import (
    _ann_delta_formula_latex,
    _ann_final_forecast_formula_latex,
    _ann_magnitude_formula_latex,
    _continuation_sgn,
    _predict_ann_computed_sgn_overrides,
    _normalize_ann_signal_rows,
    _observed_point_tooltip_columns,
    _parse_ann_train_stdout_tables,
    _format_selected_magnitude,
    _selected_point_tooltip_columns,
    _resolve_map_computed_sgn,
    _sgn_class_explanation_markdown,
    _sgn_suggested_real_sgn_markdown,
    _sgn_map_status_note,
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
        {
            "Ticker": "TNX",
            "Computed SGN": "+",
            "Realized SGN": "-",
            "Magnitude": "0.1000",
        },
        {
            "Ticker": "DJI",
            "Computed SGN": "-",
            "Realized SGN": "+",
            "Magnitude": "0.2000",
        },
        {
            "Ticker": "SPX",
            "Computed SGN": "",
            "Realized SGN": "",
            "Magnitude": "",
        },
    ]

    out = _normalize_ann_signal_rows(rows)

    assert out[0]["Computed SGN"] == "+1"
    assert out[0]["Realized SGN"] == "-1"
    assert out[1]["Computed SGN"] == "-1"
    assert out[1]["Realized SGN"] == "+1"
    assert out[2]["Computed SGN"] == "N/A"
    assert out[2]["Realized SGN"] == "N/A"


def test_resolve_map_computed_sgn_prefers_real_vs_computed_payload() -> None:
    ann_rows = [{"Ticker": "DJI", "Computed SGN": "+"}]
    compare_rows = [{"Ticker": "DJI", "Computed SGN": "-"}]
    assert _resolve_map_computed_sgn("DJI", ann_rows, compare_rows) == "-"


def test_resolve_map_computed_sgn_fallback_derives_trend_from_t0_and_p() -> None:
    ann_rows = [{"Ticker": "DJI", "T0": "10", "P": "9"}]
    compare_rows: list[dict[str, str]] = []
    assert _resolve_map_computed_sgn("DJI", ann_rows, compare_rows) == "-"


def test_continuation_sgn_uses_survival_semantics() -> None:
    assert _continuation_sgn(trend_sign="+", realized_or_predicted_sign="+") == "+"
    assert _continuation_sgn(trend_sign="-", realized_or_predicted_sign="-") == "+"
    assert _continuation_sgn(trend_sign="+", realized_or_predicted_sign="-") == "-"
    assert _continuation_sgn(trend_sign="-", realized_or_predicted_sign="+") == "-"
    assert _continuation_sgn(trend_sign="", realized_or_predicted_sign="+") == ""


def test_predict_ann_computed_sgn_overrides_uses_suggestion_and_trend(
    monkeypatch,
) -> None:
    def _fake_prepare_context(**kwargs):
        return {"ticker": str(kwargs.get("ticker") or "").upper()}

    def _fake_evaluate_context(**kwargs):
        context = kwargs.get("context") or {}
        ticker = str(context.get("ticker") or "")
        if ticker == "DJI":
            return {"suggested_real_sgn": {"value": "+1", "confidence": 0.9}}
        return {"suggested_real_sgn": {"value": "-1", "confidence": 0.8}}

    monkeypatch.setattr(
        "src.ui.services.ann_sgn_compute.prepare_sgn_probability_context",
        _fake_prepare_context,
    )
    monkeypatch.setattr(
        "src.ui.services.ann_sgn_compute.evaluate_sgn_suggestion_from_context",
        _fake_evaluate_context,
    )
    out = _predict_ann_computed_sgn_overrides(
        selected_date="2026-04-07",
        tickers=["DJI", "TNX"],
        compare_rows=[
            {"Ticker": "DJI", "Computed SGN": "-"},
            {"Ticker": "TNX", "Computed SGN": "+"},
        ],
    )
    overrides = out["computed_sgn_overrides"]
    assert overrides["DJI"] == "-"
    assert overrides["TNX"] == "-"


def test_sgn_map_status_note_warns_for_diagnostic_only_payload() -> None:
    level, text = _sgn_map_status_note(
        {
            "metrics": {
                "sample_count": 24,
                "agreement_rate": 0.62,
                "edge_count": 10,
                "edge_accuracy": 0.41,
                "diagnostic_only": True,
            }
        }
    )
    assert level == "warning"
    assert "Diagnostic-only map" in text


def test_sgn_map_status_note_success_for_healthy_payload() -> None:
    level, text = _sgn_map_status_note(
        {
            "metrics": {
                "sample_count": 42,
                "agreement_rate": 0.83,
                "edge_count": 8,
                "edge_accuracy": 0.75,
                "diagnostic_only": False,
            }
        }
    )
    assert level == "success"
    assert "SGN map ready" in text


def test_sgn_class_explanation_markdown_contains_all_class_meanings() -> None:
    text = _sgn_class_explanation_markdown()
    assert "pp = real:+, computed:+" in text
    assert "pn = real:+, computed:-" in text
    assert "np = real:-, computed:+" in text
    assert "nn = real:-, computed:-" in text


def test_sgn_suggested_real_sgn_markdown_renders_probabilities_and_suggestion() -> None:
    text = _sgn_suggested_real_sgn_markdown(
        {
            "selected_point": {"available": True, "as_of_date": "2025-08-19"},
            "conditional_real_prob": {
                "available": True,
                "computed_sgn": "-1",
                "p_real_pos": 0.36,
                "p_real_neg": 0.64,
            },
            "suggested_real_sgn": {
                "value": "-1",
                "confidence": 0.64,
                "low_confidence": False,
            },
        }
    )
    assert "P(real=+1 | computed sign=-1, U,V) = 0.360" in text
    assert "P(real=-1 | computed sign=-1, U,V) = 0.640" in text
    assert "Suggested real SGN: -1" in text


def test_selected_point_tooltip_columns_include_magnitude_label() -> None:
    columns = _selected_point_tooltip_columns()
    magnitude = [x for x in columns if x.get("title") == "M"]
    assert len(magnitude) == 1
    assert magnitude[0]["field"] == "magnitude_label"


def test_observed_point_tooltip_columns_include_magnitude_label() -> None:
    columns = _observed_point_tooltip_columns()
    magnitude = [x for x in columns if x.get("title") == "M"]
    assert len(magnitude) == 1
    assert magnitude[0]["field"] == "magnitude_label"


def test_format_selected_magnitude_normalizes_and_fallbacks() -> None:
    assert _format_selected_magnitude("0.466") == "0.4660"
    assert _format_selected_magnitude(1.2) == "1.2000"
    assert _format_selected_magnitude("") == "N/A"
    assert _format_selected_magnitude("N/A") == "N/A"


def test_ann_formula_latex_strings_include_expected_terms() -> None:
    magnitude = _ann_magnitude_formula_latex()
    delta = _ann_delta_formula_latex()
    forecast = _ann_final_forecast_formula_latex()

    assert "Magnitude" in magnitude
    assert "T_0" in magnitude
    assert "P" in magnitude

    assert "Delta" in delta
    assert "T_0" in delta
    assert "C_{+3}" in delta

    assert "FF" in forecast
    assert "T_0" in forecast
    assert "TrendDir" in forecast
    assert "SGN" in forecast
    assert "Magnitude" in forecast
