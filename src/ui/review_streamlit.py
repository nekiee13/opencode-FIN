from __future__ import annotations

import html
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from src.ui.services.ann_epoch_config import (
    epochs_for_ticker_mode,
    load_epoch_rows,
    save_epoch_rows,
    validate_epoch_rows,
)
from src.config import paths
from src.ui.services.ann_ops import (
    extract_ann_train_run_dir,
    load_ann_store_summary,
    load_ann_train_artifacts,
    run_ann_feature_stores_ingest,
    run_ann_markers_ingest,
    run_ann_train,
    run_ann_tune,
)
from src.ui.services.ann_info import (
    build_ann_guides_markdown,
    build_ann_info_rows,
    load_ann_info,
)
from src.ui.services.ann_report import (
    export_ann_report_markdown,
    load_ann_report_sections,
)
from src.ui.services.ann_sgn_compute import (
    continuation_sgn,
    predict_ann_computed_sgn_overrides,
)
from src.ui.services.ann_stats import compute_ann_overall_stats
from src.ui.services.ann_sgn_map import (
    build_sgn_probability_map,
    write_sgn_map_artifacts,
)
from src.ui.services.anchored_backfill import run_anchored_backfill
from src.ui.services.dashboard_loader import (
    build_marker_comparison_rows,
    load_marker_values,
    load_model_table,
    load_weighted_ensemble_values,
)
from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.pipeline_runner import (
    TICKER_ORDER,
    build_pipeline_commands,
    run_command,
)
from src.ui.services.pipeline_qa import evaluate_pipeline_state, write_pipeline_qa_log
from src.ui.services.round_status import compute_round_status
from src.ui.services.run_registry import (
    append_stage_result,
    create_run,
    finalize_run,
    list_runs,
    load_run,
)
from src.ui.services.vg_loader import (
    build_ann_real_vs_computed_rows,
    build_ann_t0_p_sgn_rows,
    format_blue_table_rows,
    format_green_table_rows,
    format_violet_blue_rows,
    green_meta_to_rows,
    list_violet_forecast_dates,
    materialize_for_selected_date,
    matrix_to_rows,
    pick_anchored_violet_date,
    resolve_target_forecast_date,
)


def _streamlit() -> Any:
    import streamlit as st  # type: ignore

    return st


def _status_color(status: str) -> str:
    value = str(status or "").upper()
    if value == "GREEN":
        return "#13a10e"
    if value == "BLUE":
        return "#0078d4"
    if value == "RED":
        return "#d13438"
    if value == "VIOLET":
        return "#7f39fb"
    return "#666666"


def _global_right_align_css() -> str:
    return """
<style>
/* Global text/header alignment */
div[data-testid="stAppViewContainer"] h1,
div[data-testid="stAppViewContainer"] h2,
div[data-testid="stAppViewContainer"] h3,
div[data-testid="stAppViewContainer"] h4,
div[data-testid="stAppViewContainer"] h5,
div[data-testid="stAppViewContainer"] h6,
div[data-testid="stAppViewContainer"] p,
div[data-testid="stAppViewContainer"] label,
div[data-testid="stAppViewContainer"] .stMarkdown,
div[data-testid="stAppViewContainer"] .stCaption,
div[data-testid="stAppViewContainer"] .stTabs,
div[data-testid="stAppViewContainer"] .stTabs [role="tab"],
div[data-testid="stAppViewContainer"] .stSelectbox label,
div[data-testid="stAppViewContainer"] .stNumberInput label,
div[data-testid="stAppViewContainer"] .stTextInput label,
div[data-testid="stAppViewContainer"] .stButton button,
div[data-testid="stAppViewContainer"] .stSelectbox,
div[data-testid="stAppViewContainer"] .stNumberInput,
div[data-testid="stAppViewContainer"] .stTextInput {
  text-align: right !important;
}

/* DataFrame / table headers and values */
div[data-testid="stDataFrame"] [role="columnheader"],
div[data-testid="stDataFrame"] [role="gridcell"],
div[data-testid="stDataFrame"] [role="rowheader"],
div[data-testid="stDataFrameGlideDataEditor"] [role="columnheader"],
div[data-testid="stDataFrameGlideDataEditor"] [role="gridcell"],
div[data-testid="stDataFrameGlideDataEditor"] [role="rowheader"],
div[data-testid="stDataFrameGlideDataEditor"] [data-testid="StyledDataFrameCell"],
div[data-testid="stTable"] th,
div[data-testid="stTable"] td {
  text-align: right !important;
  justify-content: flex-end !important;
}

/* Metric widgets */
div[data-testid="stMetricLabel"],
div[data-testid="stMetricValue"] {
  text-align: right !important;
  justify-content: flex-end !important;
  width: 100% !important;
}

/* Local override for Pipeline QA block */
div[data-testid="stAppViewContainer"] .pipeline-qa-left,
div[data-testid="stAppViewContainer"] .pipeline-qa-left * {
  text-align: left !important;
  justify-content: flex-start !important;
}

div[data-testid="stAppViewContainer"] .pipeline-qa-left pre {
  white-space: pre-wrap;
  word-break: break-word;
}

/* JSON payload blocks are always left aligned */
div[data-testid="stAppViewContainer"] .json-left,
div[data-testid="stAppViewContainer"] .json-left * {
  text-align: left !important;
  justify-content: flex-start !important;
}

div[data-testid="stAppViewContainer"] .json-left pre {
  white-space: pre-wrap;
  word-break: break-word;
}

/* Training stdout/stderr blocks are left aligned */
div[data-testid="stAppViewContainer"] .log-left,
div[data-testid="stAppViewContainer"] .log-left * {
  text-align: left !important;
  justify-content: flex-start !important;
}

div[data-testid="stAppViewContainer"] .log-left pre {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
""".strip()


def _apply_global_right_alignment(st: Any) -> None:
    st.markdown(_global_right_align_css(), unsafe_allow_html=True)


def _style_table_rows(rows: list[dict[str, Any]], text_color: str) -> Any:
    if not rows:
        return rows
    try:
        import pandas as pd  # type: ignore

        frame = pd.DataFrame(rows)
        cols = [c for c in list(frame.columns) if str(c) != "Ticker"]
        if not cols:
            return frame
        return frame.style.apply(
            lambda row: [
                "" if str(col) == "Ticker" else f"color: {text_color};"
                for col in list(frame.columns)
            ],
            axis=1,
        )
    except Exception:
        return rows


def _render_aligned_table(st: Any, data: Any) -> None:
    try:
        import pandas as pd  # type: ignore

        if hasattr(data, "set_table_styles") and hasattr(data, "set_properties"):
            styled = data.set_table_styles(
                [
                    {"selector": "th", "props": [("text-align", "right")]},
                    {"selector": "td", "props": [("text-align", "right")]},
                ],
                overwrite=False,
            ).set_properties(**{"text-align": "right"})
            st.table(styled)
            return

        frame = data if hasattr(data, "columns") else pd.DataFrame(data)
        styled = frame.style.set_table_styles(
            [
                {"selector": "th", "props": [("text-align", "right")]},
                {"selector": "td", "props": [("text-align", "right")]},
            ]
        ).set_properties(**{"text-align": "right"})
        st.table(styled)
        return
    except Exception:
        st.table(data)


def _render_json_payload(st: Any, payload: Any) -> None:
    text = json.dumps(payload, indent=2)
    st.markdown(
        "<div class='json-left'><pre>" + html.escape(text) + "</pre></div>",
        unsafe_allow_html=True,
    )


def _render_log_payload(st: Any, text: str) -> None:
    content = str(text or "") or "<empty>"
    st.markdown(
        "<div class='log-left'><pre>" + html.escape(content) + "</pre></div>",
        unsafe_allow_html=True,
    )


def _run_with_elapsed_progress(
    st: Any,
    *,
    label: str,
    fn: Any,
) -> tuple[dict[str, Any], float]:
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            value = fn()
            if isinstance(value, dict):
                result_box["result"] = value
            else:
                result_box["result"] = {"returncode": 1, "stdout": "", "stderr": ""}
        except BaseException as exc:
            error_box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    start = time.monotonic()
    bar = st.progress(0.0, text=f"{label} (0.0s elapsed)")
    while thread.is_alive():
        elapsed = time.monotonic() - start
        pulse = min(0.95, (elapsed % 20.0) / 20.0)
        bar.progress(pulse, text=f"{label} ({elapsed:.1f}s elapsed)")
        time.sleep(0.2)

    thread.join()
    elapsed_total = time.monotonic() - start
    bar.progress(1.0, text=f"{label} complete ({elapsed_total:.1f}s)")
    if "error" in error_box:
        raise error_box["error"]

    result = result_box.get("result")
    if not isinstance(result, dict):
        result = {"returncode": 1, "stdout": "", "stderr": ""}
    return result, float(elapsed_total)


def _target_modes_from_selection(target_mode: str) -> list[str]:
    value = str(target_mode or "").strip().lower()
    if value == "all":
        return ["magnitude", "sgn"]
    if value == "sgn":
        return ["sgn"]
    return ["magnitude"]


def _coerce_row_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(x) for x in value if isinstance(x, dict)]
    if hasattr(value, "to_dict"):
        try:
            payload = value.to_dict("records")
            if isinstance(payload, list):
                return [dict(x) for x in payload if isinstance(x, dict)]
        except Exception:
            return []
    return []


def _summarize_ann_training_health(
    info_payload: dict[str, Any],
    *,
    target_modes: list[str],
) -> tuple[str, str]:
    tickers_payload = info_payload.get("tickers")
    if not isinstance(tickers_payload, dict) or not tickers_payload:
        return (
            "warning",
            "ANN training completed, but no tuning status is available for selected scope.",
        )

    requested_modes = [str(x).strip().lower() for x in target_modes if str(x).strip()]
    if not requested_modes:
        requested_modes = ["magnitude"]

    failed_entries: list[str] = []
    unknown_entries: list[str] = []
    checked_entries: list[str] = []

    for ticker, payload in sorted(tickers_payload.items()):
        if not isinstance(payload, dict):
            continue
        matrix = payload.get("tune_matrix")
        matrix_dict = matrix if isinstance(matrix, dict) else {}
        for mode in requested_modes:
            mode_payload = matrix_dict.get(mode)
            mode_dict = mode_payload if isinstance(mode_payload, dict) else {}
            status = str(mode_dict.get("status") or "").strip().lower()
            key = f"{ticker}/{mode}"
            if status in {"fails_baseline", "insufficient_data"}:
                failed_entries.append(f"{key}={status}")
            elif status == "healthy":
                checked_entries.append(f"{key}=healthy")
            else:
                unknown_entries.append(f"{key}=missing")

    if failed_entries:
        return (
            "error",
            "ANN training completed but status is unsuccessful: "
            + "; ".join(failed_entries),
        )
    if checked_entries and not unknown_entries:
        return (
            "success",
            "ANN training completed successfully for requested mode(s): "
            + ", ".join(requested_modes),
        )
    return (
        "warning",
        "ANN training completed, but status could not be confirmed for all selections: "
        + "; ".join(unknown_entries),
    )


def _parse_ann_train_stdout_tables(
    stdout_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = str(stdout_text or "")
    if not text.strip():
        return [], []

    segments = [seg.strip() for seg in re.split(r"(?=\[mode=)", text) if seg.strip()]
    if not segments:
        segments = [text]

    summary_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []

    for segment in segments:
        mode_match = re.search(r"\[mode=([^\]]+)\]", segment)
        mode = str(mode_match.group(1)).strip() if mode_match else "single"

        run_dir_match = re.search(r"\[ann_train\]\s+run_dir=([^\[]+)", segment)
        rows_match = re.search(r"\[ann_train\]\s+rows=(\d+)", segment)
        features_match = re.search(r"\[ann_train\]\s+features=([^\s\[]+)", segment)
        r2_match = re.search(r"\[ann_train\]\s+r2=([-+0-9.eE]+)", segment)

        if run_dir_match or rows_match or features_match or r2_match:
            summary_rows.append(
                {
                    "Mode": mode,
                    "Run Dir": str(run_dir_match.group(1)).strip()
                    if run_dir_match
                    else "",
                    "Rows": str(rows_match.group(1)).strip() if rows_match else "",
                    "Features": str(features_match.group(1)).strip()
                    if features_match
                    else "",
                    "R2": str(r2_match.group(1)).strip() if r2_match else "",
                }
            )

        for feat_match in re.finditer(
            r"\[ann_train\]\s+top_feature\s+#(\d+)\s+(.+?)\s+score=([-+0-9.eE]+)",
            segment,
        ):
            feature_rows.append(
                {
                    "Mode": mode,
                    "Rank": str(feat_match.group(1)).strip(),
                    "Feature": str(feat_match.group(2)).strip(),
                    "Score": str(feat_match.group(3)).strip(),
                }
            )

    return summary_rows, feature_rows


def _normalize_ann_signal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def _norm_sgn(raw: Any) -> str:
        sgn_raw = str(raw or "").strip()
        if sgn_raw == "+":
            return "+1"
        if sgn_raw == "-":
            return "-1"
        if sgn_raw == "0":
            return "0"
        return "N/A"

    for row in rows:
        item = dict(row)
        if "Computed SGN" in item:
            item["Computed SGN"] = _norm_sgn(item.get("Computed SGN"))
        if "Realized SGN" in item:
            item["Realized SGN"] = _norm_sgn(item.get("Realized SGN"))
        if "SGN" in item:
            item["SGN"] = _norm_sgn(item.get("SGN"))
        out.append(item)
    return out


def _resolve_map_computed_sgn(
    map_ticker: str,
    ann_signal_rows: list[dict[str, Any]],
    compare_rows: list[dict[str, Any]],
) -> str:
    ticker_u = str(map_ticker or "").strip().upper()
    compare_map = {
        str(row.get("Ticker") or "").strip().upper(): str(
            row.get("Computed SGN") or ""
        ).strip()
        for row in compare_rows
    }
    value = str(compare_map.get(ticker_u) or "").strip()
    if value:
        return value

    ann_map = {
        str(row.get("Ticker") or "").strip().upper(): row for row in ann_signal_rows
    }
    row = ann_map.get(ticker_u) if isinstance(ann_map.get(ticker_u), dict) else {}
    t0_text = str((row or {}).get("T0") or "").strip().replace(",", "")
    p_text = str((row or {}).get("P") or "").strip().replace(",", "")
    try:
        t0 = float(t0_text)
        p = float(p_text)
    except Exception:
        return ""
    if p > t0:
        return "+"
    if p < t0:
        return "-"
    return ""


def _continuation_sgn(*, trend_sign: str, realized_or_predicted_sign: str) -> str:
    return continuation_sgn(
        trend_sign=trend_sign,
        realized_or_predicted_sign=realized_or_predicted_sign,
    )


def _predict_ann_computed_sgn_overrides(
    *,
    selected_date: str,
    tickers: list[str],
    compare_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return predict_ann_computed_sgn_overrides(
        selected_date=selected_date,
        tickers=tickers,
        compare_rows=compare_rows,
    )


def _ann_magnitude_formula_latex() -> str:
    return r"\mathrm{Magnitude} = \left|T_0 - P\right|"


def _ann_delta_formula_latex() -> str:
    return r"\mathrm{Delta} = \left|T_0 - C_{+3}\right|"


def _ann_final_forecast_formula_latex() -> str:
    return r"\mathrm{FF} = T_0 + \mathrm{TrendDir} \cdot \mathrm{SGN}_{computed} \cdot \mathrm{Magnitude}"


def _format_selected_magnitude(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "N/A"
    if text.upper() == "N/A":
        return "N/A"
    normalized = text.replace(",", "")
    try:
        value = float(normalized)
    except Exception:
        return text
    if value != value or value == float("inf") or value == float("-inf"):
        return "N/A"
    return f"{value:.4f}"


def _selected_point_tooltip_columns() -> list[dict[str, str]]:
    return [
        {"field": "as_of_date", "type": "N", "title": "Selected As-Of"},
        {"field": "computed_sgn", "type": "N", "title": "Computed SGN"},
        {"field": "pred_class", "type": "N", "title": "Map Class"},
        {"field": "max_prob", "type": "Q", "title": "Max Prob", "format": ".3f"},
        {"field": "magnitude_label", "type": "N", "title": "M"},
    ]


def _selected_point_tooltips(alt: Any) -> list[Any]:
    out: list[Any] = []
    for item in _selected_point_tooltip_columns():
        field = str(item.get("field") or "")
        if not field:
            continue
        data_type = str(item.get("type") or "N")
        title = str(item.get("title") or field)
        fmt = str(item.get("format") or "").strip()
        if fmt:
            out.append(alt.Tooltip(f"{field}:{data_type}", title=title, format=fmt))
        else:
            out.append(alt.Tooltip(f"{field}:{data_type}", title=title))
    return out


def _observed_point_tooltip_columns() -> list[dict[str, str]]:
    return [
        {"field": "as_of_date", "type": "N", "title": "As-Of"},
        {"field": "class_id", "type": "N", "title": "Teacher Class"},
        {"field": "pred_class", "type": "N", "title": "Surrogate Class"},
        {"field": "max_prob", "type": "Q", "title": "Max Prob", "format": ".3f"},
        {"field": "magnitude_label", "type": "N", "title": "M"},
    ]


def _observed_point_tooltips(alt: Any) -> list[Any]:
    out: list[Any] = []
    for item in _observed_point_tooltip_columns():
        field = str(item.get("field") or "")
        if not field:
            continue
        data_type = str(item.get("type") or "N")
        title = str(item.get("title") or field)
        fmt = str(item.get("format") or "").strip()
        if fmt:
            out.append(alt.Tooltip(f"{field}:{data_type}", title=title, format=fmt))
        else:
            out.append(alt.Tooltip(f"{field}:{data_type}", title=title))
    return out


def _sgn_class_explanation_markdown() -> str:
    return "\n".join(
        [
            "- `pp = real:+, computed:+`",
            "- `pn = real:+, computed:-`",
            "- `np = real:-, computed:+`",
            "- `nn = real:-, computed:-`",
        ]
    )


def _sgn_map_status_note(payload: dict[str, Any]) -> tuple[str, str]:
    metrics_raw = payload.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
    sample_count = int(metrics.get("sample_count") or 0)
    agreement = float(metrics.get("agreement_rate") or 0.0)
    edge_count = int(metrics.get("edge_count") or 0)
    edge_accuracy = float(metrics.get("edge_accuracy") or 0.0)
    diagnostic_only = bool(metrics.get("diagnostic_only"))

    if sample_count <= 0:
        return (
            "warning",
            "No SGN samples were available for the selected ticker/window.",
        )
    if diagnostic_only:
        return (
            "warning",
            f"Diagnostic-only map (agreement={agreement:.2%}, edge_count={edge_count}, edge_accuracy={edge_accuracy:.2%}).",
        )
    return (
        "success",
        f"SGN map ready (agreement={agreement:.2%}, edge_count={edge_count}, edge_accuracy={edge_accuracy:.2%}).",
    )


def _sgn_suggested_real_sgn_markdown(payload: dict[str, Any]) -> str:
    selected_raw = payload.get("selected_point")
    selected = selected_raw if isinstance(selected_raw, dict) else {}
    if not bool(selected.get("available")):
        reason = str(selected.get("reason") or "unavailable")
        return f"Selected ticker/date point unavailable (`{reason}`)."

    conditional_raw = payload.get("conditional_real_prob")
    conditional = conditional_raw if isinstance(conditional_raw, dict) else {}
    suggestion_raw = payload.get("suggested_real_sgn")
    suggestion = suggestion_raw if isinstance(suggestion_raw, dict) else {}

    if not bool(conditional.get("available")):
        reason = str(conditional.get("reason") or "computed_sgn_unavailable")
        return (
            "Selected point is projected, but conditional real-SGN probabilities are unavailable "
            f"(`{reason}`)."
        )

    p_real_pos = float(conditional.get("p_real_pos") or 0.0)
    p_real_neg = float(conditional.get("p_real_neg") or 0.0)
    computed_sgn = str(conditional.get("computed_sgn") or "N/A")
    suggested = str(suggestion.get("value") or "N/A")
    confidence = float(suggestion.get("confidence") or 0.0)
    low_conf = bool(suggestion.get("low_confidence"))
    qualifier = " (low confidence)" if low_conf else ""

    return "\n".join(
        [
            f"- `P(real=+1 | computed sign={computed_sgn}, U,V) = {p_real_pos:.3f}`",
            f"- `P(real=-1 | computed sign={computed_sgn}, U,V) = {p_real_neg:.3f}`",
            f"- **Suggested real SGN: {suggested} (confidence {confidence:.1%}){qualifier}**",
        ]
    )


def _render_sgn_map_chart(st: Any, payload: dict[str, Any]) -> None:
    points = list(payload.get("points") or [])
    grid = list(payload.get("grid") or [])
    if not points or not grid:
        st.info("No SGN map points/grid available.")
        return

    try:
        import altair as alt  # type: ignore
    except Exception:
        st.info("Altair is unavailable in this runtime; rendering SGN map as tables.")
        _render_aligned_table(st, points[:50])
        return

    observed_points: list[dict[str, Any]] = []
    for row in points:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["magnitude_label"] = _format_selected_magnitude(
            item.get("magnitude_label")
        )
        observed_points.append(item)

    class_colors = {
        "pp": "#2ca25f",
        "pn": "#f03b20",
        "np": "#2b8cbe",
        "nn": "#756bb1",
    }
    domain = ["pp", "pn", "np", "nn"]
    color_scale = alt.Scale(
        domain=domain,
        range=[class_colors[x] for x in domain],
    )

    base = (
        alt.Chart(alt.Data(values=grid))
        .mark_square(size=60)
        .encode(
            x=alt.X("U:Q", title="Composite U"),
            y=alt.Y("V:Q", title="Composite V"),
            color=alt.Color("pred_class:N", scale=color_scale, title="Class region"),
            opacity=alt.Opacity(
                "max_prob:Q",
                title="Max probability",
                scale=alt.Scale(domain=[0.0, 1.0], range=[0.20, 0.95]),
            ),
            tooltip=[
                alt.Tooltip("U:Q", format=".3f"),
                alt.Tooltip("V:Q", format=".3f"),
                alt.Tooltip("pred_class:N", title="Class"),
                alt.Tooltip("max_prob:Q", format=".3f"),
            ],
        )
    )

    observed = (
        alt.Chart(alt.Data(values=observed_points))
        .mark_circle(
            size=70,
            color="#FFFFFF",
            opacity=0.95,
            stroke="#111111",
            strokeWidth=1.0,
        )
        .encode(
            x=alt.X("U:Q"),
            y=alt.Y("V:Q"),
            tooltip=_observed_point_tooltips(alt),
        )
    )
    chart = base + observed

    selected_raw = payload.get("selected_point")
    selected = selected_raw if isinstance(selected_raw, dict) else {}
    if bool(selected.get("available")):
        selected = dict(selected)
        selected["magnitude_label"] = _format_selected_magnitude(
            selected.get("magnitude_label")
        )
        selected_layer = (
            alt.Chart(alt.Data(values=[selected]))
            .mark_point(
                shape="diamond",
                size=320,
                color="#ffd166",
                stroke="#111111",
                strokeWidth=1.8,
                filled=True,
            )
            .encode(
                x=alt.X("U:Q"),
                y=alt.Y("V:Q"),
                tooltip=_selected_point_tooltips(alt),
            )
        )
        chart = chart + selected_layer

    st.altair_chart(chart.properties(height=420), use_container_width=True)


def _render_sgn_map_diagnostics(st: Any, payload: dict[str, Any]) -> None:
    metrics_raw = payload.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Samples", int(metrics.get("sample_count") or 0))
    c2.metric("Agreement", f"{float(metrics.get('agreement_rate') or 0.0):.2%}")
    c3.metric("Macro F1", f"{float(metrics.get('macro_f1') or 0.0):.3f}")
    c4.metric("Edge Accuracy", f"{float(metrics.get('edge_accuracy') or 0.0):.2%}")

    weights = payload.get("weights")
    if isinstance(weights, dict):
        st.markdown("**Composite Weights (U/V)**")
        rows: list[dict[str, Any]] = []
        for axis in ("U", "V"):
            entries = weights.get(axis)
            if not isinstance(entries, list):
                continue
            for item in entries:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    {
                        "Axis": axis,
                        "Feature": str(item.get("feature") or ""),
                        "Weight": float(item.get("weight") or 0.0),
                        "Score": float(item.get("score") or 0.0),
                        "Utility": float(item.get("utility") or 0.0),
                        "Stability": float(item.get("stability") or 0.0),
                    }
                )
        if rows:
            _render_aligned_table(st, rows)


def _render_round_status(st: Any, status_payload: dict[str, Any]) -> None:
    status = str(status_payload.get("status") or "UNKNOWN")
    reason = str(status_payload.get("reason") or "")
    index_code = str(status_payload.get("index_code") or "").strip()
    color = _status_color(status)
    st.markdown(
        f"<div style='padding:0.5rem 0.75rem;border-radius:8px;border:1px solid {color};'>"
        f"<b>ROUND STATUS:</b> <span style='color:{color};font-weight:700;'>{status}</span></div>",
        unsafe_allow_html=True,
    )
    if reason:
        st.caption(reason)
    if index_code:
        st.caption(f"Index: {index_code}")
    missing = list(status_payload.get("missing_tickers") or [])
    if missing:
        st.caption("Missing tickers: " + ", ".join(missing))
    log_id = str(status_payload.get("log_id") or "").strip()
    if log_id:
        st.caption(f"see log #{log_id}")


def _render_command_results(st: Any, run_payload: dict[str, Any] | None) -> None:
    if not run_payload:
        st.info("No command execution records yet.")
        return

    results = list(run_payload.get("stages", []))
    run_id = str(run_payload.get("run_id") or "")
    st.caption(f"run_id={run_id}")

    ok_count = sum(1 for row in results if str(row.get("status") or "") == "success")
    failed_count = sum(1 for row in results if str(row.get("status") or "") == "failed")
    st.caption(
        f"Stages: {len(results)} | Succeeded: {ok_count} | Failed: {failed_count}"
    )

    failed_rows = [row for row in results if str(row.get("status") or "") == "failed"]
    if failed_rows:
        st.error("One or more stages failed. Details are listed below.")
        _render_aligned_table(
            st,
            [
                {
                    "stage": row.get("stage"),
                    "ticker": row.get("ticker"),
                    "returncode": row.get("returncode"),
                    "reason_code": row.get("reason_code"),
                    "log_id": row.get("log_id"),
                    "log_path": row.get("log_path"),
                }
                for row in failed_rows
            ],
        )

    for item in results:
        ticker = str(item.get("ticker") or "-")
        stage = str(item.get("stage") or "-")
        rc = int(item.get("returncode", 0))
        reason_code = str(item.get("reason_code") or "")
        log_id = str(item.get("log_id") or "")
        label = f"{stage} | ticker={ticker} | rc={rc} | {reason_code or 'NONE'}"
        with st.expander(label):
            if log_id:
                st.caption(f"log_id={log_id}")
            st.caption(f"log_path={item.get('log_path')}")
            st.text("Command")
            _render_log_payload(st, " ".join(item.get("command", [])))
            st.text("stdout")
            _render_log_payload(st, str(item.get("stdout", "") or ""))
            st.text("stderr")
            _render_log_payload(st, str(item.get("stderr", "") or ""))


def run_review_console(db_path: Path | None = None) -> None:
    _ = db_path
    st = _streamlit()

    st.set_page_config(page_title="FIN Streamlit Console", layout="wide")
    st.title("FIN Streamlit Console")
    _apply_global_right_alignment(st)

    date_options = load_sidebar_date_options()
    if not date_options:
        date_options = [""]

    with st.sidebar:
        st.subheader("Context")
        selected_date = st.selectbox("Date", date_options, key="ctx_date")
        selected_ticker = st.selectbox(
            "Ticker",
            ["ALL", *TICKER_ORDER],
            key="ctx_ticker",
        )
        _render_round_status(
            st,
            compute_round_status(selected_date=selected_date),
        )

    tab_ml, tab_dashboard, tab_vg, tab_ann, tab_report = st.tabs(
        ["ML Calculations", "Dashboard", "Blue/Green ML", "ANN", "Report"]
    )

    with tab_ml:
        st.subheader("ML Calculations")
        st.caption("Execution uses selected sidebar date and ticker scope.")
        if st.button("Run ML Pipeline", key="run_ml_pipeline"):
            specs = build_pipeline_commands(
                selected_date=selected_date,
                selected_ticker=selected_ticker,
            )
            run_payload = create_run(
                selected_date=selected_date,
                selected_ticker=selected_ticker,
                total_stages=len(specs),
            )
            run_id = str(run_payload["run_id"])
            st.session_state["ml_pipeline_run_id"] = run_id

            progress_bar = st.progress(0.0)
            status_placeholder = st.empty()

            for index, spec in enumerate(specs, start=1):
                status_placeholder.info(
                    f"Running stage {index}/{len(specs)}: {spec.stage} (ticker={spec.ticker or '-'})"
                )
                result = run_command(spec)
                append_stage_result(
                    run_id=run_id,
                    stage_index=index,
                    stage_name=spec.stage,
                    category=spec.category,
                    ticker=spec.ticker,
                    command=spec.command,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_seconds=round(result.duration_seconds, 3),
                )
                progress_bar.progress(float(index) / float(max(len(specs), 1)))

            finished = finalize_run(run_id)
            if str(finished.get("status") or "") == "success":
                status_placeholder.success("Pipeline run completed successfully.")
            else:
                status_placeholder.error("Pipeline run completed with failures.")

        st.caption(
            "Anchored backfill builds follow-up round artifacts for selected date and ingests/materializes VG in one flow."
        )
        if st.button("Run Anchored Backfill", key="run_anchored_backfill"):
            progress_slot = st.empty()
            status_slot = st.empty()
            progress = progress_slot.progress(0, text="Anchored backfill 0/4: starting")

            def _on_backfill_progress(step: int, total: int, stage: str) -> None:
                safe_total = max(int(total), 1)
                safe_step = max(0, min(int(step), safe_total))
                ratio = float(safe_step) / float(safe_total)
                label = str(stage or "stage")
                progress.progress(
                    ratio, text=f"Anchored backfill {safe_step}/{safe_total}: {label}"
                )

            result = run_anchored_backfill(
                selected_date=selected_date,
                selected_ticker=selected_ticker,
                progress_callback=_on_backfill_progress,
            )
            if str(result.get("status") or "") == "success":
                progress.progress(1.0, text="Anchored backfill 4/4: done")
                status_slot.success("Anchored backfill finished.")
            else:
                status_slot.error("Anchored backfill failed.")
            st.session_state["anchored_backfill_result"] = result

        anchored_result = st.session_state.get("anchored_backfill_result")
        if isinstance(anchored_result, dict):
            if str(anchored_result.get("status") or "") == "success":
                st.success(
                    "Anchored backfill completed: "
                    f"round_id={anchored_result.get('round_id')} "
                    f"forecast_date={anchored_result.get('forecast_date')}"
                )
            else:
                st.error(
                    "Anchored backfill failed: "
                    + str(anchored_result.get("index_code") or "BACKFILL_ERROR")
                )
            _render_json_payload(st, anchored_result)

        run_id = str(st.session_state.get("ml_pipeline_run_id") or "").strip()
        _render_command_results(st, load_run(run_id) if run_id else None)

        st.subheader("Recent Runs")
        history = list_runs(limit=10, selected_date=selected_date)
        if not history:
            st.info("No persisted runs found for selected date.")
        else:
            _render_aligned_table(
                st,
                [
                    {
                        "run_id": item.get("run_id"),
                        "status": item.get("status"),
                        "total_stages": item.get("total_stages"),
                        "completed_stages": item.get("completed_stages"),
                        "failed_stages": item.get("failed_stages"),
                        "created_at": item.get("created_at"),
                        "ended_at": item.get("ended_at"),
                    }
                    for item in history
                ],
            )

        st.markdown(
            "<div class='pipeline-qa-left'><h3>Pipeline QA</h3></div>",
            unsafe_allow_html=True,
        )
        qa_report = evaluate_pipeline_state(selected_date=selected_date)
        qa_report_json = json.dumps(qa_report, indent=2)
        st.markdown(
            "<div class='pipeline-qa-left'><pre>"
            + html.escape(qa_report_json)
            + "</pre></div>",
            unsafe_allow_html=True,
        )

        if st.button("Write QA Log", key="write_pipeline_qa_log"):
            qa_path = write_pipeline_qa_log(report=qa_report)
            st.session_state["qa_log_path"] = str(qa_path)

        qa_log_path = str(st.session_state.get("qa_log_path") or "").strip()
        if qa_log_path:
            st.caption(f"QA log: {qa_log_path}")

    with tab_dashboard:
        st.subheader("ML Dashboard")
        model_table = load_model_table(selected_date)
        if model_table.rows:
            st.caption(
                f"Round: {model_table.source_round_id or 'N/A'} | As-of: {model_table.asof_date or 'N/A'}"
            )
            _render_aligned_table(st, model_table.rows)
        else:
            st.warning("No model table rows were found for selected date context.")

        marker_values = load_marker_values(selected_date)
        ml_weighted_values = load_weighted_ensemble_values(selected_date)
        comparison_rows = build_marker_comparison_rows(
            model_rows=model_table.rows,
            marker_values=marker_values,
            ml_values_by_ticker=ml_weighted_values,
        )
        st.subheader("Marker Comparison: Oraclum / RD / 85220")
        _render_aligned_table(st, comparison_rows)

    with tab_vg:
        st.subheader("Blue / Green / Violet ML Tables")
        st.caption(
            "Violet = true accuracy. Blue = transformed Violet (continuous piecewise interpolation). "
            "Green = moving average with dummy warm-up slots."
        )
        available_violet_dates = list_violet_forecast_dates()
        target_forecast_date = resolve_target_forecast_date(
            selected_date=selected_date,
            fh3_dir=paths.OUT_I_CALC_FH3_DIR,
        )
        anchored_forecast_date = pick_anchored_violet_date(
            selected_date=selected_date,
            available_dates=available_violet_dates,
            fh3_dir=paths.OUT_I_CALC_FH3_DIR,
        )
        has_violet_dates = len(available_violet_dates) > 0
        has_anchored_violet = False
        if not available_violet_dates:
            st.warning(
                "No violet rows currently available. Run finalize+ingest to populate Violet scores."
            )
            st.caption("Index: IDX_VIOLET_MISSING")
            st.text_input(
                "Forecast Date (available violet rounds)",
                value="",
                key="vg_forecast_date_select_empty",
                disabled=True,
            )
            forecast_date = ""
            st.session_state["vg_error"] = ""
        elif not anchored_forecast_date:
            st.warning(
                "No violet rows exist for the selected round anchor. "
                "Run finalize+ingest for this selected date context."
            )
            st.caption(
                f"Selected date: {selected_date} | target forecast date: {target_forecast_date}"
            )
            st.caption("Index: IDX_VIOLET_MISSING")
            st.text_input(
                "Forecast Date (anchored violet round)",
                value="",
                key="vg_forecast_date_select_unanchored",
                disabled=True,
            )
            st.caption(
                "Available violet dates: " + ", ".join(available_violet_dates[:12])
            )
            forecast_date = ""
            st.session_state["vg_error"] = ""
        else:
            forecast_date = str(anchored_forecast_date)
            st.text_input(
                "Forecast Date (anchored violet round)",
                value=forecast_date,
                key="vg_forecast_date_select_anchored",
                disabled=True,
            )
            has_anchored_violet = True
            if selected_date and str(forecast_date) != str(selected_date):
                st.info(
                    f"Selected round date {selected_date} maps to anchored forecast date {forecast_date}."
                )

        warmup_depth = st.selectbox(
            "Warm-up Depth (dummy slot window)",
            options=[3, 4, 5],
            index=1,
            key="vg_warmup_depth",
        )

        run_clicked = st.button(
            "Load Blue/Green",
            key="load_blue_green",
            disabled=not has_anchored_violet,
        )
        if run_clicked:
            try:
                result, elapsed_seconds = _run_with_elapsed_progress(
                    st,
                    label="Load Blue/Green in progress",
                    fn=lambda: materialize_for_selected_date(
                        selected_date=selected_date,
                        forecast_date=forecast_date or None,
                        fh3_dir=paths.OUT_I_CALC_FH3_DIR,
                        memory_tail=int(warmup_depth),
                        bootstrap_enabled=True,
                        policy_name="value_assign_v1",
                    ),
                )
                result["elapsed_seconds"] = float(round(elapsed_seconds, 3))
                st.session_state["vg_result"] = result
                st.session_state["vg_error"] = ""
            except Exception as exc:
                st.session_state["vg_error"] = str(exc)
                if has_violet_dates:
                    st.session_state["vg_error"] += (
                        "\nAvailable violet dates: "
                        + ", ".join(available_violet_dates[:12])
                    )

        vg_error = str(st.session_state.get("vg_error", "") or "")
        if vg_error:
            st.error(vg_error)

        vg_result = st.session_state.get("vg_result")
        if isinstance(vg_result, dict):
            st.caption(
                f"forecast_date={vg_result.get('forecast_date')} | policy={vg_result.get('policy_name')} "
                f"({vg_result.get('policy_mode')}) | memory_tail={vg_result.get('memory_tail')}"
            )
            st.caption(
                f"real_data_start={vg_result.get('real_data_start_date', '2025-07-29')}"
            )
            models = [str(x) for x in vg_result.get("models", [])]
            tickers = [str(x) for x in vg_result.get("tickers", [])]
            violet_rows = matrix_to_rows(
                matrix=dict(vg_result.get("violet", {})),
                models=models,
                tickers=tickers,
            )
            violet_rows = format_violet_blue_rows(violet_rows)
            blue_rows = matrix_to_rows(
                matrix=dict(vg_result.get("blue", {})),
                models=models,
                tickers=tickers,
            )
            blue_rows = format_blue_table_rows(blue_rows)
            green_rows = matrix_to_rows(
                matrix=dict(vg_result.get("green", {})),
                models=models,
                tickers=tickers,
            )
            green_rows = format_green_table_rows(green_rows)
            green_meta_rows = green_meta_to_rows(
                green_meta=dict(vg_result.get("green_meta", {})),
                models=models,
                tickers=tickers,
            )
            st.markdown("**Violet Table (True Accuracy)**")
            _render_aligned_table(st, _style_table_rows(violet_rows, "#9b59ff"))
            st.markdown("**Blue Table**")
            _render_aligned_table(st, _style_table_rows(blue_rows, "#4aa8ff"))
            st.markdown("**Green Table**")
            _render_aligned_table(st, _style_table_rows(green_rows, "#2ecc71"))
            st.markdown("**Green Provenance (Real vs Dummy Slots)**")
            _render_aligned_table(st, green_meta_rows)

    with tab_ann:
        st.subheader("ANN")

        compare_rows_for_map = build_ann_real_vs_computed_rows(
            selected_date=selected_date,
            tickers=list(TICKER_ORDER),
        )

        computed_sgn_by_date_raw = st.session_state.get("ann_computed_sgn_by_date")
        computed_sgn_by_date = (
            dict(computed_sgn_by_date_raw)
            if isinstance(computed_sgn_by_date_raw, dict)
            else {}
        )
        date_key = str(selected_date or "").strip()
        date_overrides_raw = computed_sgn_by_date.get(date_key)
        date_overrides = (
            dict(date_overrides_raw) if isinstance(date_overrides_raw, dict) else {}
        )

        ann_signal_rows = build_ann_t0_p_sgn_rows(
            selected_date=selected_date,
            tickers=list(TICKER_ORDER),
            computed_sgn_overrides=date_overrides,
        )
        st.markdown(
            "**T0 / P / Final Forecast / +3-day / Computed SGN / Realized SGN / Magnitude / Delta**"
        )
        _render_aligned_table(st, _normalize_ann_signal_rows(ann_signal_rows))
        st.latex(_ann_magnitude_formula_latex())
        st.latex(_ann_delta_formula_latex())
        st.latex(_ann_final_forecast_formula_latex())
        st.caption(
            "T0 = close on selected date, P = weighted day+1 ensemble prediction."
        )

        if st.button("Compute SGN", key="run_ann_compute_sgn"):
            try:
                result, elapsed_seconds = _run_with_elapsed_progress(
                    st,
                    label="Computing ANN SGN",
                    fn=lambda: _predict_ann_computed_sgn_overrides(
                        selected_date=str(selected_date or "").strip(),
                        tickers=list(TICKER_ORDER),
                        compare_rows=compare_rows_for_map,
                    ),
                )
                overrides_raw = result.get("computed_sgn_overrides")
                overrides = (
                    dict(overrides_raw) if isinstance(overrides_raw, dict) else {}
                )
                computed_sgn_by_date[date_key] = overrides
                st.session_state["ann_computed_sgn_by_date"] = computed_sgn_by_date
                st.session_state["ann_compute_sgn_details"] = list(
                    result.get("details") or []
                )
                st.session_state["ann_compute_sgn_elapsed"] = float(
                    round(elapsed_seconds, 3)
                )
                st.session_state["ann_compute_sgn_error"] = ""
                if hasattr(st, "rerun"):
                    st.rerun()
            except Exception as exc:
                st.session_state["ann_compute_sgn_error"] = str(exc)

        compute_err = str(st.session_state.get("ann_compute_sgn_error", "") or "")
        if compute_err:
            st.error("Compute SGN failed: " + compute_err)

        details_raw = st.session_state.get("ann_compute_sgn_details")
        details = details_raw if isinstance(details_raw, list) else []
        if details:
            elapsed = float(st.session_state.get("ann_compute_sgn_elapsed") or 0.0)
            st.caption(
                f"Compute SGN completed in {elapsed:.2f}s for {len(details)} tickers."
            )

        store_path = paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"
        summary = load_ann_store_summary(store_path)
        c1, c2, c3 = st.columns(3)

        families = dict(summary.get("families") or {})
        total_rows = 0
        latest_dates: list[str] = []
        for payload in families.values():
            if not isinstance(payload, dict):
                continue
            total_rows += int(payload.get("rows") or 0)
            latest_value = str(payload.get("latest_as_of_date") or "").strip()
            if latest_value:
                latest_dates.append(latest_value)

        c1.metric("Store Exists", "Yes" if summary["exists"] else "No")
        c2.metric("Rows", int(total_rows))
        c3.metric("Latest As-Of", max(latest_dates) if latest_dates else "N/A")
        st.caption(str(summary["store_path"]))

        if families:
            _render_aligned_table(
                st,
                [
                    {
                        "family": str(name),
                        "rows": int(payload.get("rows") or 0),
                        "latest_as_of_date": str(
                            payload.get("latest_as_of_date") or "N/A"
                        ),
                    }
                    for name, payload in families.items()
                    if isinstance(payload, dict)
                ],
            )

        info_col, compare_col = st.columns(2)
        if info_col.button("Info", key="show_ann_info"):
            st.session_state["ann_show_info"] = True
        if compare_col.button("Compare", key="show_ann_compare"):
            st.session_state["ann_show_compare"] = True

        if bool(st.session_state.get("ann_show_info")):
            info_payload = load_ann_info(
                selected_ticker=selected_ticker,
                tickers=list(TICKER_ORDER),
                store_summary=summary,
            )
            scope_raw = info_payload.get("scope")
            scope: dict[str, Any] = scope_raw if isinstance(scope_raw, dict) else {}
            selected_scope = [
                str(x)
                for x in list(scope.get("selected_tickers") or [])
                if str(x).strip()
            ]
            st.markdown("**ANN Setup Info**")
            st.caption(
                "Scope: " + (", ".join(selected_scope) if selected_scope else "N/A")
            )
            info_rows = build_ann_info_rows(info_payload)
            if info_rows:
                _render_aligned_table(st, info_rows)
            else:
                st.info("No ANN setup artifacts were found for selected ticker scope.")

            profile_raw = info_payload.get("profile")
            profile_payload: dict[str, Any] = (
                profile_raw if isinstance(profile_raw, dict) else {}
            )
            if profile_payload:
                st.caption(
                    "Profile active: "
                    + ("Yes" if bool(profile_payload.get("is_active")) else "No")
                    + f" | selected features: {int(profile_payload.get('selected_feature_count') or 0)}"
                )

            with st.expander("ANN Info (raw JSON)"):
                _render_json_payload(st, info_payload)

            st.markdown(build_ann_guides_markdown())

        if bool(st.session_state.get("ann_show_compare")):
            st.markdown("**Real vs Computed (SGN / Magnitude)**")
            st.caption(
                "Computed values are derived from ANN P prediction against T0; "
                "Real values are derived from realized +3-day actual close against T0."
            )
            _render_aligned_table(st, compare_rows_for_map)

        if st.button("Compute ANN Overall Stats", key="run_ann_overall_stats"):
            try:
                stats_payload, elapsed_seconds = _run_with_elapsed_progress(
                    st,
                    label="Computing ANN overall stats",
                    fn=lambda: compute_ann_overall_stats(tickers=list(TICKER_ORDER)),
                )
                stats_payload["elapsed_seconds"] = float(round(elapsed_seconds, 3))
                st.session_state["ann_overall_stats"] = stats_payload
                st.session_state["ann_overall_stats_error"] = ""
            except Exception as exc:
                st.session_state["ann_overall_stats_error"] = str(exc)

        stats_err = str(st.session_state.get("ann_overall_stats_error", "") or "")
        if stats_err:
            st.error("ANN overall stats failed: " + stats_err)

        overall_raw = st.session_state.get("ann_overall_stats")
        overall = overall_raw if isinstance(overall_raw, dict) else None
        if overall:
            st.markdown("**ANN SGN Success (All Tickers/Dates)**")
            st.metric("SGN Success", str(overall.get("success_label") or "0/0 (N/A)"))
            st.caption(
                f"computed in {float(overall.get('elapsed_seconds') or 0.0):.2f}s across {int(overall.get('dates_count') or 0)} dates"
            )
            st.markdown("**Avg |Delta - Magnitude| and % Delta > Magnitude**")
            gap_rows = list(
                overall.get("magnitude_gap_rows")
                or overall.get("magnitude_ratio_rows")
                or []
            )
            if gap_rows:
                _render_aligned_table(st, gap_rows)

            st.markdown("**Failed SGN Log**")
            st.caption(f"rows: {int(overall.get('failed_sgn_count') or 0)}")
            failed_rows = list(overall.get("failed_sgn_rows") or [])
            if failed_rows:
                _render_aligned_table(st, failed_rows)

        st.markdown("**SGN Confidence Map (2D)**")
        sgn_col1, sgn_col2, sgn_col3, sgn_col4 = st.columns(4)
        map_ticker = sgn_col1.selectbox(
            "Map Ticker",
            options=list(TICKER_ORDER),
            index=0,
            key="ann_sgn_map_ticker",
        )
        map_grid_size = int(
            sgn_col2.number_input(
                "Grid Size",
                min_value=10,
                max_value=80,
                value=35,
                step=5,
                key="ann_sgn_map_grid_size",
            )
        )
        map_neighbors = int(
            sgn_col3.number_input(
                "K Neighbors",
                min_value=3,
                max_value=31,
                value=9,
                step=2,
                key="ann_sgn_map_neighbors",
            )
        )
        map_edge_threshold = float(
            sgn_col4.number_input(
                "Edge Threshold",
                min_value=0.40,
                max_value=0.95,
                value=0.60,
                step=0.05,
                key="ann_sgn_map_edge_threshold",
            )
        )

        sgn_col5, sgn_col6 = st.columns(2)
        map_max_features = int(
            sgn_col5.number_input(
                "Max Features",
                min_value=2,
                max_value=20,
                value=10,
                step=1,
                key="ann_sgn_map_max_features",
            )
        )
        map_rolling_window = int(
            sgn_col6.number_input(
                "Rolling Window",
                min_value=4,
                max_value=120,
                value=20,
                step=1,
                key="ann_sgn_map_rolling_window",
            )
        )

        signal_by_ticker = {
            str(row.get("Ticker") or "").strip().upper(): row for row in ann_signal_rows
        }
        map_signal_row = signal_by_ticker.get(str(map_ticker).strip().upper(), {})
        map_computed_sgn = _resolve_map_computed_sgn(
            str(map_ticker),
            ann_signal_rows,
            compare_rows_for_map,
        )
        map_magnitude = _format_selected_magnitude(map_signal_row.get("Magnitude"))

        if st.button("Build SGN Map", key="run_ann_sgn_map"):
            try:
                payload, elapsed_seconds = _run_with_elapsed_progress(
                    st,
                    label="Building SGN map",
                    fn=lambda: build_sgn_probability_map(
                        ticker=str(map_ticker),
                        grid_size=int(map_grid_size),
                        max_features=int(map_max_features),
                        k_neighbors=int(map_neighbors),
                        edge_threshold=float(map_edge_threshold),
                        rolling_window=int(map_rolling_window),
                        selected_date=str(selected_date or "").strip(),
                        computed_sgn=map_computed_sgn,
                    ),
                )
                selected_raw = payload.get("selected_point")
                if isinstance(selected_raw, dict):
                    selected_point = dict(selected_raw)
                    selected_point["magnitude_label"] = map_magnitude
                    payload["selected_point"] = selected_point
                payload["elapsed_seconds"] = float(round(elapsed_seconds, 3))
                st.session_state["ann_sgn_map_payload"] = payload
                st.session_state["ann_sgn_map_error"] = ""
            except Exception as exc:
                st.session_state["ann_sgn_map_error"] = str(exc)

        sgn_err = str(st.session_state.get("ann_sgn_map_error", "") or "")
        if sgn_err:
            st.error("SGN map build failed: " + sgn_err)

        sgn_payload_raw = st.session_state.get("ann_sgn_map_payload")
        sgn_payload = sgn_payload_raw if isinstance(sgn_payload_raw, dict) else None
        if sgn_payload:
            status_level, status_text = _sgn_map_status_note(sgn_payload)
            if status_level == "success":
                st.success(status_text)
            else:
                st.warning(status_text)
            st.caption(
                f"Build time: {float(sgn_payload.get('elapsed_seconds') or 0.0):.2f}s"
            )
            _render_sgn_map_chart(st, sgn_payload)
            st.markdown(_sgn_suggested_real_sgn_markdown(sgn_payload))
            st.markdown(_sgn_class_explanation_markdown())
            _render_sgn_map_diagnostics(st, sgn_payload)

            if st.button("Export SGN Map Artifacts", key="export_ann_sgn_map"):
                now_tag = str(int(time.time()))
                out_dir = (
                    paths.OUT_I_CALC_DIR
                    / "ANN"
                    / "sgn_map"
                    / str(sgn_payload.get("ticker") or map_ticker)
                    / now_tag
                )
                export_paths = write_sgn_map_artifacts(
                    payload=sgn_payload, output_dir=out_dir
                )
                st.session_state["ann_sgn_map_export"] = export_paths

            export_paths_raw = st.session_state.get("ann_sgn_map_export")
            export_paths = (
                export_paths_raw if isinstance(export_paths_raw, dict) else None
            )
            if export_paths:
                st.caption("SGN map artifacts exported.")
                _render_aligned_table(
                    st,
                    [
                        {"artifact": key, "path": value}
                        for key, value in export_paths.items()
                    ],
                )

        if st.button("Run ANN Feature Ingest", key="run_ann_feature_ingest"):
            result = run_ann_feature_stores_ingest(store_path=store_path)
            st.session_state["ann_ingest_result"] = result

        if st.button("Run ANN Marker Ingest (Legacy)", key="run_ann_marker_ingest"):
            marker_store = paths.OUT_I_CALC_DIR / "stores" / "ann_markers_store.sqlite"
            result = run_ann_markers_ingest(store_path=marker_store)
            st.session_state["ann_ingest_result"] = result

        profile_dir = paths.OUT_I_CALC_DIR / "ann" / "feature_profiles"
        profile_path = profile_dir / "pruned_inputs.json"
        profile_active = profile_path.exists()
        st.caption(
            "Input Profile: "
            + (f"Pruned ({profile_path})" if profile_active else "Full feature set")
        )

        epoch_rows_raw, epoch_load_errors, epoch_path = load_epoch_rows()
        st.caption(f"Epoch Config: {epoch_path}")
        if epoch_load_errors:
            st.warning("Epoch config had issues and was reset to defaults.")
        epoch_editor_value = st.data_editor(
            list(epoch_rows_raw),
            key="ann_epoch_editor",
            use_container_width=True,
            hide_index=True,
            disabled=["Ticker"],
            num_rows="fixed",
        )
        epoch_editor_rows = _coerce_row_records(epoch_editor_value) or list(
            epoch_rows_raw
        )
        epoch_rows_validated, epoch_validation_errors = validate_epoch_rows(
            epoch_editor_rows
        )
        if st.button("Save Epoch Config", key="save_ann_epoch_config"):
            saved_rows, save_errors, saved_path = save_epoch_rows(epoch_editor_rows)
            if save_errors:
                st.error("Failed to save epoch config: " + "; ".join(save_errors[:3]))
            else:
                st.session_state["ann_epoch_saved_rows"] = list(saved_rows)
                st.success(f"Epoch config saved: {saved_path}")

        (
            ann_train_col1,
            ann_train_col2,
            ann_train_col3,
            ann_train_col4,
            ann_train_col5,
            ann_train_col6,
        ) = st.columns(6)
        ann_window_length = ann_train_col1.number_input(
            "Window Length",
            min_value=1,
            max_value=30,
            value=5,
            step=1,
            key="ann_window_length",
        )
        ann_lag_depth = ann_train_col2.number_input(
            "Lag Depth",
            min_value=0,
            max_value=30,
            value=4,
            step=1,
            key="ann_lag_depth",
        )
        ann_max_trials = ann_train_col3.number_input(
            "Tune Max Trials",
            min_value=1,
            max_value=200,
            value=20,
            step=1,
            key="ann_max_trials",
        )
        ann_end_date_options = [str(x) for x in date_options if str(x).strip()]
        default_end_date = str(selected_date or "").strip()
        default_end_index = 0
        if ann_end_date_options:
            if default_end_date in ann_end_date_options:
                default_end_index = ann_end_date_options.index(default_end_date)
            else:
                default_end_index = len(ann_end_date_options) - 1
        ann_train_end_date = ann_train_col4.selectbox(
            "Train End Date",
            options=ann_end_date_options if ann_end_date_options else [""],
            index=default_end_index,
            key="ann_train_end_date",
        )
        ann_target_mode = ann_train_col5.selectbox(
            "Target Mode",
            options=["magnitude", "sgn", "all"],
            index=0,
            key="ann_target_mode",
        )
        ann_prune_keep_ratio = ann_train_col6.number_input(
            "Prune Keep Ratio",
            min_value=0.10,
            max_value=0.95,
            value=0.50,
            step=0.05,
            key="ann_prune_keep_ratio",
        )

        if st.button("Prune Inputs", key="run_ann_prune_inputs"):
            selected_scope = (
                list(TICKER_ORDER)
                if str(selected_ticker).strip().upper() in {"", "ALL", "ALL_TICKERS"}
                else [str(selected_ticker).strip().upper()]
            )
            selected_modes = _target_modes_from_selection(str(ann_target_mode))
            result = run_ann_train(
                tickers=selected_scope,
                window_length=int(ann_window_length),
                lag_depth=int(ann_lag_depth),
                train_end_date=str(ann_train_end_date or "").strip() or None,
                target_mode=str(selected_modes[0]),
                feature_selection="importance",
                importance_keep_ratio=float(ann_prune_keep_ratio),
                save_selected_features_file=profile_path,
            )
            st.session_state["ann_ingest_result"] = result

        if st.button("Reset ANN", key="run_ann_reset"):
            if profile_path.exists():
                profile_path.unlink()
                st.success("ANN input profile reset to full feature set.")
            else:
                st.info("ANN input profile already using full feature set.")

        if st.button("Run ANN Train", key="run_ann_train"):
            selected_scope = (
                list(TICKER_ORDER)
                if str(selected_ticker).strip().upper() in {"", "ALL", "ALL_TICKERS"}
                else [str(selected_ticker).strip().upper()]
            )
            selected_modes = _target_modes_from_selection(str(ann_target_mode))
            if epoch_validation_errors:
                st.error(
                    "Epoch config invalid: "
                    + "; ".join([str(x) for x in epoch_validation_errors[:4]])
                )
                selected_modes = []
            mode_runs: list[dict[str, Any]] = []
            combined_stdout: list[str] = []
            combined_stderr: list[str] = []
            total_elapsed = 0.0
            for ticker in selected_scope:
                for mode in selected_modes:
                    epochs_value = epochs_for_ticker_mode(
                        epoch_rows_validated,
                        ticker=ticker,
                        mode=mode,
                        fallback=200 if mode == "sgn" else 600,
                    )
                    run_result, elapsed_seconds = _run_with_elapsed_progress(
                        st,
                        label=f"ANN training in progress ({ticker}:{mode}:{epochs_value})",
                        fn=lambda current_mode=mode, current_ticker=ticker, current_epochs=epochs_value: (
                            run_ann_train(
                                tickers=[current_ticker],
                                window_length=int(ann_window_length),
                                lag_depth=int(ann_lag_depth),
                                epochs=int(current_epochs),
                                train_end_date=str(ann_train_end_date or "").strip()
                                or None,
                                target_mode=str(current_mode),
                                feature_allowlist_file=profile_path
                                if profile_path.exists()
                                else None,
                            )
                        ),
                    )
                    run_result["target_mode"] = mode
                    run_result["ticker"] = ticker
                    run_result["epochs"] = int(epochs_value)
                    run_result["elapsed_seconds"] = float(round(elapsed_seconds, 3))
                    mode_runs.append(run_result)
                    total_elapsed += float(elapsed_seconds)
                    combined_stdout.append(
                        f"[ticker={ticker} mode={mode} epochs={int(epochs_value)}]\n{str(run_result.get('stdout', '') or '')}".strip()
                    )
                    combined_stderr.append(
                        f"[ticker={ticker} mode={mode} epochs={int(epochs_value)}]\n{str(run_result.get('stderr', '') or '')}".strip()
                    )

            if not mode_runs:
                result = {
                    "returncode": 1,
                    "target_modes": list(selected_modes),
                    "mode_runs": [],
                    "command": [],
                    "stdout": "",
                    "stderr": "No ANN training runs executed.",
                    "elapsed_seconds": 0.0,
                }
            else:
                returncode = 0
                for item in mode_runs:
                    if int(item.get("returncode") or 0) != 0:
                        returncode = int(item.get("returncode") or 1)
                        break
                result = {
                    "returncode": int(returncode),
                    "target_modes": list(selected_modes),
                    "mode_runs": mode_runs,
                    "command": [item.get("command") for item in mode_runs],
                    "stdout": "\n\n".join(combined_stdout).strip(),
                    "stderr": "\n\n".join(combined_stderr).strip(),
                    "elapsed_seconds": float(round(total_elapsed, 3)),
                }
            st.session_state["ann_ingest_result"] = result

            if int(result.get("returncode") or 0) != 0:
                st.session_state["ann_train_feedback"] = {
                    "level": "error",
                    "text": "ANN training failed. Check stderr details below.",
                }
            else:
                info_payload = load_ann_info(
                    selected_ticker=selected_ticker,
                    tickers=list(TICKER_ORDER),
                    store_summary=summary,
                )
                level, text = _summarize_ann_training_health(
                    info_payload,
                    target_modes=selected_modes,
                )
                st.session_state["ann_train_feedback"] = {
                    "level": level,
                    "text": text,
                }

        feedback_raw = st.session_state.get("ann_train_feedback")
        feedback = feedback_raw if isinstance(feedback_raw, dict) else None
        if feedback:
            level = str(feedback.get("level") or "info").strip().lower()
            text = str(feedback.get("text") or "").strip()
            if text:
                if level == "success":
                    st.success(text)
                elif level == "error":
                    st.error(text)
                elif level == "warning":
                    st.warning(text)
                else:
                    st.info(text)

                if "insufficient_data" in text or "fails_baseline" in text:
                    st.markdown(
                        "- `insufficient_data`: setup failed minimum data gates (sample size/class balance/target variance)."
                        "\n- `fails_baseline`: ANN did not beat naive baseline by required margin."
                    )

        if st.button("Run ANN Tune", key="run_ann_tune"):
            result = run_ann_tune(max_trials=int(ann_max_trials))
            st.session_state["ann_ingest_result"] = result

        ann_result = st.session_state.get("ann_ingest_result")
        if isinstance(ann_result, dict):
            _render_json_payload(
                st,
                {
                    "returncode": ann_result.get("returncode"),
                    "command": ann_result.get("command"),
                    "elapsed_seconds": ann_result.get("elapsed_seconds"),
                },
            )
            st.text("stdout")
            stdout_text = str(ann_result.get("stdout", "") or "")
            summary_rows, feature_rows = _parse_ann_train_stdout_tables(stdout_text)
            if summary_rows:
                _render_aligned_table(st, summary_rows)
            if feature_rows:
                st.markdown("**Top Features (Parsed)**")
                _render_aligned_table(st, feature_rows)
            if not summary_rows and not feature_rows:
                _render_log_payload(st, stdout_text)
            st.text("stderr")
            _render_log_payload(st, str(ann_result.get("stderr", "") or ""))

            run_dir = extract_ann_train_run_dir(str(ann_result.get("stdout", "") or ""))
            if run_dir is not None and run_dir.exists():
                artifacts = load_ann_train_artifacts(run_dir)
                top = list(artifacts.get("top_feature_impacts") or [])
                if top:
                    st.markdown("**Top 5 Input Impact**")
                    _render_aligned_table(st, top[:5])

    with tab_report:
        st.subheader("Report")
        st.caption(
            "Per-ticker ANN report with real-vs-computed comparison and best setup details."
        )
        if st.button("Export", key="export_ann_report"):
            try:
                export_payload = export_ann_report_markdown(
                    selected_date=selected_date,
                    selected_ticker=selected_ticker,
                    tickers=list(TICKER_ORDER),
                )
                st.session_state["ann_report_export"] = export_payload
            except Exception as exc:
                st.session_state["ann_report_export"] = {"error": str(exc)}

        export_state_raw = st.session_state.get("ann_report_export")
        export_state = export_state_raw if isinstance(export_state_raw, dict) else {}
        if export_state:
            err = str(export_state.get("error") or "").strip()
            if err:
                st.error("Report export failed: " + err)
            else:
                st.success(
                    "Report exported: " + str(export_state.get("output_path") or "")
                )

        report_payload = load_ann_report_sections(
            selected_date=selected_date,
            tickers=list(TICKER_ORDER),
        )
        tune_run_id = str(report_payload.get("latest_tune_run_id") or "").strip()
        if tune_run_id:
            st.caption(f"Latest tune run: {tune_run_id}")

        sections_raw = report_payload.get("sections")
        sections = sections_raw if isinstance(sections_raw, dict) else {}
        for ticker in TICKER_ORDER:
            payload_raw = sections.get(ticker)
            payload = payload_raw if isinstance(payload_raw, dict) else {}
            st.markdown(f"### {ticker}")

            st.markdown("**Real vs Computed (SGN / Magnitude)**")
            compare_row = payload.get("compare_row")
            compare = (
                compare_row if isinstance(compare_row, dict) else {"Ticker": ticker}
            )
            _render_aligned_table(st, [compare])

            st.markdown("**Best ANN Setup Details**")
            setup_rows_raw = payload.get("best_setup_rows")
            setup_rows = setup_rows_raw if isinstance(setup_rows_raw, list) else []
            if setup_rows:
                _render_aligned_table(st, setup_rows)
            else:
                st.info("No setup details available.")

            status_note = str(payload.get("status_note") or "").strip()
            if status_note:
                st.caption("Status note: " + status_note)
            st.markdown("---")
