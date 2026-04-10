from __future__ import annotations

import html
import json
import threading
import time
from pathlib import Path
from typing import Any

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
            st.code(" ".join(item.get("command", [])), language="bash")
            st.text("stdout")
            st.code(str(item.get("stdout", "")) or "<empty>")
            st.text("stderr")
            st.code(str(item.get("stderr", "")) or "<empty>")


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

    tab_ml, tab_dashboard, tab_vg, tab_ann = st.tabs(
        ["ML Calculations", "Dashboard", "Blue/Green ML", "ANN"]
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
                result = materialize_for_selected_date(
                    selected_date=selected_date,
                    forecast_date=forecast_date or None,
                    fh3_dir=paths.OUT_I_CALC_FH3_DIR,
                    memory_tail=int(warmup_depth),
                    bootstrap_enabled=True,
                    policy_name="value_assign_v1",
                )
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

        ann_signal_rows = build_ann_t0_p_sgn_rows(
            selected_date=selected_date,
            tickers=list(TICKER_ORDER),
        )
        st.markdown("**T0 / P / +3-day / Delta / SGN / Magnitude**")
        _render_aligned_table(st, ann_signal_rows)

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
            compare_rows = build_ann_real_vs_computed_rows(
                selected_date=selected_date,
                tickers=list(TICKER_ORDER),
            )
            st.markdown("**Real vs Computed (SGN / Magnitude)**")
            st.caption(
                "Computed values are derived from ANN P prediction against T0; "
                "Real values are derived from realized +3-day actual close against T0."
            )
            _render_aligned_table(st, compare_rows)

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
            mode_runs: list[dict[str, Any]] = []
            combined_stdout: list[str] = []
            combined_stderr: list[str] = []
            total_elapsed = 0.0
            for mode in selected_modes:
                run_result, elapsed_seconds = _run_with_elapsed_progress(
                    st,
                    label=f"ANN training in progress ({mode})",
                    fn=lambda current_mode=mode: run_ann_train(
                        tickers=selected_scope,
                        window_length=int(ann_window_length),
                        lag_depth=int(ann_lag_depth),
                        train_end_date=str(ann_train_end_date or "").strip() or None,
                        target_mode=str(current_mode),
                        feature_allowlist_file=profile_path
                        if profile_path.exists()
                        else None,
                    ),
                )
                run_result["target_mode"] = mode
                run_result["elapsed_seconds"] = float(round(elapsed_seconds, 3))
                mode_runs.append(run_result)
                total_elapsed += float(elapsed_seconds)
                combined_stdout.append(
                    f"[mode={mode}]\n{str(run_result.get('stdout', '') or '')}".strip()
                )
                combined_stderr.append(
                    f"[mode={mode}]\n{str(run_result.get('stderr', '') or '')}".strip()
                )

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
            _render_log_payload(st, str(ann_result.get("stdout", "") or ""))
            st.text("stderr")
            _render_log_payload(st, str(ann_result.get("stderr", "") or ""))

            run_dir = extract_ann_train_run_dir(str(ann_result.get("stdout", "") or ""))
            if run_dir is not None and run_dir.exists():
                artifacts = load_ann_train_artifacts(run_dir)
                top = list(artifacts.get("top_feature_impacts") or [])
                if top:
                    st.markdown("**Top 5 Input Impact**")
                    _render_aligned_table(st, top[:5])
