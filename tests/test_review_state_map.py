from __future__ import annotations

from src.review.state_map import map_round_state


def test_map_round_state_draft_is_editable() -> None:
    out = map_round_state("DRAFT_T0")
    assert out.raw_round_state == "DRAFT_T0"
    assert out.gui_state == "EDIT"
    assert out.editable is True


def test_map_round_state_final_is_show_only() -> None:
    out = map_round_state("FINAL_TPLUS3")
    assert out.gui_state == "SHOW"
    assert out.editable is False


def test_map_round_state_unknown_defaults_to_show_with_warning() -> None:
    out = map_round_state("UNSEEN_STATE")
    assert out.gui_state == "SHOW"
    assert out.editable is False
    assert "unknown" in out.reason.lower()
