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
from src.ui.services.vg_loader import materialize_for_selected_date, matrix_to_rows


def _streamlit() -> Any:
    import streamlit as st  # type: ignore

    return st


def _render_command_results(st: Any, results: list[dict[str, Any]]) -> None:
    if not results:
        st.info("No command execution records yet.")
        return

    ok_count = sum(1 for row in results if int(row.get("returncode", 1)) == 0)
    st.caption(
        f"Stages: {len(results)} | Succeeded: {ok_count} | Failed: {len(results) - ok_count}"
    )
    for item in results:
        ticker = str(item.get("ticker") or "-")
        stage = str(item.get("stage") or "-")
        rc = int(item.get("returncode", 1))
        label = f"{stage} | ticker={ticker} | rc={rc}"
        with st.expander(label):
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
            collected: list[dict[str, Any]] = []
            for spec in specs:
                result = run_command(spec)
                collected.append(
                    {
                        "category": spec.category,
                        "stage": spec.stage,
                        "ticker": spec.ticker,
                        "command": spec.command,
                        "returncode": result.returncode,
                        "duration_seconds": round(result.duration_seconds, 3),
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
            st.session_state["ml_pipeline_results"] = collected

        _render_command_results(
            st, list(st.session_state.get("ml_pipeline_results", []))
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
        st.subheader("Blue and Green ML Tables")
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

        if st.button("Load Blue/Green", key="load_blue_green"):
            try:
                result = materialize_for_selected_date(
                    selected_date=selected_date,
                    forecast_date=forecast_date or None,
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
                f"forecast_date={vg_result.get('forecast_date')} | policy={vg_result.get('policy_name')}"
            )
            models = [str(x) for x in vg_result.get("models", [])]
            tickers = [str(x) for x in vg_result.get("tickers", [])]
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
            st.markdown("**Blue Table**")
            st.dataframe(blue_rows, use_container_width=True)
            st.markdown("**Green Table**")
            st.dataframe(green_rows, use_container_width=True)

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
