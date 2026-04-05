from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.ann_ops import load_ann_store_summary, run_ann_markers_ingest
from src.ui.services.dashboard_loader import (
    build_marker_comparison_rows,
    load_marker_values,
    load_model_table,
)
from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.pipeline_runner import (
    TICKER_ORDER,
    build_pipeline_commands,
    run_command,
)
from src.ui.services.round_status import compute_round_status
from src.ui.services.run_registry import (
    append_stage_result,
    create_run,
    finalize_run,
    list_runs,
    load_run,
)
from src.ui.services.vg_loader import (
    green_meta_to_rows,
    materialize_for_selected_date,
    matrix_to_rows,
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
        st.dataframe(
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
            use_container_width=True,
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
        ["ML Calculations", "Dashboard", "Blue/Green ML", "ANN Training"]
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

        run_id = str(st.session_state.get("ml_pipeline_run_id") or "").strip()
        _render_command_results(st, load_run(run_id) if run_id else None)

        st.subheader("Recent Runs")
        history = list_runs(limit=10, selected_date=selected_date)
        if not history:
            st.info("No persisted runs found for selected date.")
        else:
            st.dataframe(
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
                use_container_width=True,
            )

    with tab_dashboard:
        st.subheader("ML Dashboard")
        model_table = load_model_table(selected_date)
        if model_table.rows:
            st.caption(
                f"Round: {model_table.source_round_id or 'N/A'} | As-of: {model_table.asof_date or 'N/A'}"
            )
            st.dataframe(model_table.rows, use_container_width=True)
        else:
            st.warning("No model table rows were found for selected date context.")

        marker_values = load_marker_values(selected_date)
        comparison_rows = build_marker_comparison_rows(
            model_rows=model_table.rows,
            marker_values=marker_values,
        )
        st.subheader("Marker Comparison: Oraclum / RD / 85220")
        st.dataframe(comparison_rows, use_container_width=True)

    with tab_vg:
        st.subheader("Blue / Green / Violet ML Tables")
        st.caption(
            "Violet = true accuracy. Blue = transformed Violet (continuous piecewise interpolation). "
            "Green = moving average with dummy warm-up slots."
        )
        forecast_date_default = ""
        if selected_date:
            try:
                from src.ui.services.vg_loader import next_business_day

                forecast_date_default = next_business_day(selected_date)
            except Exception:
                forecast_date_default = ""

        forecast_date = st.text_input(
            "Forecast Date (yyyy-mm-dd)",
            value=forecast_date_default,
            key="vg_forecast_date",
        )

        warmup_depth = st.selectbox(
            "Warm-up Depth (dummy slot window)",
            options=[3, 4, 5],
            index=1,
            key="vg_warmup_depth",
        )

        if st.button("Load Blue/Green", key="load_blue_green"):
            try:
                result = materialize_for_selected_date(
                    selected_date=selected_date,
                    forecast_date=forecast_date or None,
                    memory_tail=int(warmup_depth),
                    bootstrap_enabled=True,
                    policy_name="value_assign_v1",
                )
                st.session_state["vg_result"] = result
                st.session_state["vg_error"] = ""
            except Exception as exc:
                st.session_state["vg_error"] = str(exc)

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
            blue_rows = matrix_to_rows(
                matrix=dict(vg_result.get("blue", {})),
                models=models,
                tickers=tickers,
            )
            green_rows = matrix_to_rows(
                matrix=dict(vg_result.get("green", {})),
                models=models,
                tickers=tickers,
            )
            green_meta_rows = green_meta_to_rows(
                green_meta=dict(vg_result.get("green_meta", {})),
                models=models,
                tickers=tickers,
            )
            st.markdown("**Violet Table (True Accuracy)**")
            st.dataframe(violet_rows, use_container_width=True)
            st.markdown("**Blue Table**")
            st.dataframe(blue_rows, use_container_width=True)
            st.markdown("**Green Table**")
            st.dataframe(green_rows, use_container_width=True)
            st.markdown("**Green Provenance (Real vs Dummy Slots)**")
            st.dataframe(green_meta_rows, use_container_width=True)

    with tab_ann:
        st.subheader("ANN Training / Store")
        store_path = paths.OUT_I_CALC_DIR / "stores" / "ann_markers_store.sqlite"
        summary = load_ann_store_summary(store_path)
        c1, c2, c3 = st.columns(3)
        c1.metric("Store Exists", "Yes" if summary["exists"] else "No")
        c2.metric("Rows", int(summary["rows"]))
        c3.metric("Latest As-Of", str(summary["latest_as_of_date"] or "N/A"))
        st.caption(str(summary["store_path"]))

        if st.button("Run ANN Ingest", key="run_ann_ingest"):
            result = run_ann_markers_ingest(store_path=store_path)
            st.session_state["ann_ingest_result"] = result

        ann_result = st.session_state.get("ann_ingest_result")
        if isinstance(ann_result, dict):
            st.code(
                json.dumps(
                    {
                        "returncode": ann_result.get("returncode"),
                        "command": ann_result.get("command"),
                    },
                    indent=2,
                ),
                language="json",
            )
            st.text("stdout")
            st.code(str(ann_result.get("stdout", "")) or "<empty>")
            st.text("stderr")
            st.code(str(ann_result.get("stderr", "")) or "<empty>")
