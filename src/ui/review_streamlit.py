from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.ann_ops import (
    load_ann_store_summary,
    run_ann_feature_stores_ingest,
    run_ann_markers_ingest,
    run_ann_train,
    run_ann_tune,
)
from src.ui.services.anchored_backfill import run_anchored_backfill
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
            st.code(json.dumps(anchored_result, indent=2), language="json")

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

        st.subheader("Pipeline QA")
        qa_report = evaluate_pipeline_state(selected_date=selected_date)
        st.code(json.dumps(qa_report, indent=2), language="json")

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
            st.dataframe(
                _style_table_rows(violet_rows, "#9b59ff"),
                use_container_width=True,
            )
            st.markdown("**Blue Table**")
            st.dataframe(
                _style_table_rows(blue_rows, "#4aa8ff"),
                use_container_width=True,
            )
            st.markdown("**Green Table**")
            st.dataframe(
                _style_table_rows(green_rows, "#2ecc71"),
                use_container_width=True,
            )
            st.markdown("**Green Provenance (Real vs Dummy Slots)**")
            st.dataframe(green_meta_rows, use_container_width=True)

    with tab_ann:
        st.subheader("ANN Training / Store")

        ann_signal_rows = build_ann_t0_p_sgn_rows(
            selected_date=selected_date,
            tickers=list(TICKER_ORDER),
        )
        st.markdown("**T0 / P / SGN / Magnitude**")
        st.dataframe(ann_signal_rows, use_container_width=True)

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
            st.dataframe(
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
                use_container_width=True,
            )

        if st.button("Run ANN Feature Ingest", key="run_ann_feature_ingest"):
            result = run_ann_feature_stores_ingest(store_path=store_path)
            st.session_state["ann_ingest_result"] = result

        if st.button("Run ANN Marker Ingest (Legacy)", key="run_ann_marker_ingest"):
            marker_store = paths.OUT_I_CALC_DIR / "stores" / "ann_markers_store.sqlite"
            result = run_ann_markers_ingest(store_path=marker_store)
            st.session_state["ann_ingest_result"] = result

        (
            ann_train_col1,
            ann_train_col2,
            ann_train_col3,
            ann_train_col4,
            ann_train_col5,
        ) = st.columns(5)
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
            options=["magnitude", "sgn"],
            index=0,
            key="ann_target_mode",
        )

        if st.button("Run ANN Train", key="run_ann_train"):
            selected_scope = (
                list(TICKER_ORDER)
                if str(selected_ticker).strip().upper() in {"", "ALL", "ALL_TICKERS"}
                else [str(selected_ticker).strip().upper()]
            )
            result = run_ann_train(
                tickers=selected_scope,
                window_length=int(ann_window_length),
                lag_depth=int(ann_lag_depth),
                train_end_date=str(ann_train_end_date or "").strip() or None,
                target_mode=str(ann_target_mode or "magnitude").strip().lower(),
            )
            st.session_state["ann_ingest_result"] = result

        if st.button("Run ANN Tune", key="run_ann_tune"):
            result = run_ann_tune(max_trials=int(ann_max_trials))
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
