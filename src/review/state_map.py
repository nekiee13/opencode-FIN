from __future__ import annotations

from src.review.models import GuiRoundStateModel


_EDIT_STATES = {
    "DRAFT_T0",
    "PARTIAL_ACTUALS",
}

_SHOW_STATES = {
    "FINAL_TPLUS3",
    "REVISED",
}


def map_round_state(raw_round_state: str) -> GuiRoundStateModel:
    state = str(raw_round_state or "").strip().upper()
    if state in _EDIT_STATES:
        return GuiRoundStateModel(
            raw_round_state=state,
            gui_state="EDIT",
            editable=True,
            reason="Draft-like round state mapped to editable mode.",
        )
    if state in _SHOW_STATES:
        return GuiRoundStateModel(
            raw_round_state=state,
            gui_state="SHOW",
            editable=False,
            reason="Finalized round state mapped to read-only mode.",
        )
    return GuiRoundStateModel(
        raw_round_state=state,
        gui_state="SHOW",
        editable=False,
        reason="Unknown round state mapped to SHOW for safety.",
    )
