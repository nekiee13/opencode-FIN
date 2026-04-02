from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import paths
from src.review.repository import ReviewRepository
from src.review.service import (
    load_available_review_dates,
    load_available_tickers,
    validate_review_payload,
)


def _streamlit() -> Any:
    import streamlit as st  # type: ignore

    return st


def run_review_console(db_path: Path | None = None) -> None:
    st = _streamlit()
    repo = ReviewRepository(
        db_path or (paths.OUT_I_CALC_DIR / "HITL" / "HITL_review.sqlite")
    )

    st.set_page_config(page_title="FIN Review Console", layout="wide")
    st.title("FIN Review Console")

    dates = load_available_review_dates()
    tickers = load_available_tickers()

    with st.sidebar:
        st.subheader("Context")
        date_values = [item["review_date"] for item in dates]
        selected_date = st.selectbox("Date", date_values or [""], key="ctx_date")
        selected_ticker = st.selectbox("Ticker", tickers, key="ctx_ticker")
        selected_mode = st.selectbox(
            "Mode", ["ML", "ML + Human Review"], key="ctx_mode"
        )

    st.subheader("Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Selected Date", selected_date or "N/A")
    c2.metric("Ticker", selected_ticker)
    c3.metric("Mode", selected_mode)

    st.subheader("Review Input")
    with st.form("review_form"):
        manual_prediction = st.number_input(
            "Manual Prediction Override",
            value=0.0,
            step=0.1,
            key="review_manual_prediction",
        )
        manual_sgn = st.selectbox(
            "Manual SGN Override", ["+", "-"], key="review_manual_sgn"
        )
        confidence = st.slider("Confidence", 0, 100, 50, key="review_confidence")
        comment = st.text_area("Justification Comment", key="review_comment")
        submitted = st.form_submit_button("Validate")

    if submitted:
        validation = validate_review_payload(
            {
                "review_date": selected_date,
                "ticker": selected_ticker,
                "mode": selected_mode,
                "gui_state": "EDIT",
                "ai_consensus_value": None,
                "ai_consensus_sgn": None,
                "ai_consensus_strategy": "policy_selected",
                "manual_prediction_override": manual_prediction,
                "manual_sgn_override": manual_sgn,
                "confidence": confidence,
                "justification_comment": comment,
                "scenario_before": None,
                "scenario_after": None,
                "change_flag": False,
                "ann_magnitude": None,
                "ann_sgn": None,
                "source_context_path": None,
                "source_snapshot_ref": None,
            }
        )
        if validation.ok:
            st.success("Payload is valid for persistence.")
        else:
            st.error("Payload validation failed.")
            for error_text in validation.errors:
                st.write(f"- {error_text}")

    st.subheader("Audit")
    history = repo.load_audit_history(selected_date or "", selected_ticker)
    if not history.events:
        st.info("No durable review events yet for selected context.")
    else:
        rows = [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "field_name": event.field_name,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "status": event.event_status,
                "created_at": event.created_at,
            }
            for event in history.events
        ]
        st.dataframe(rows, use_container_width=True)
