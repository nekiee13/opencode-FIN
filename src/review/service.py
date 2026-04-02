from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlite3

from src.config import paths
from src.review.exports import export_payload_json_text
from src.review.models import (
    ANNSnapshotModel,
    AuditHistoryModel,
    ModelComparisonRowModel,
    ReviewPayloadModel,
    ValidationResultModel,
)
from src.review.repository import ReviewRepository
from src.review.state_map import map_round_state

_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "round_id",
        "review_date",
        "ticker",
        "mode",
        "gui_state",
        "ai_consensus_value",
        "ai_consensus_sgn",
        "ai_consensus_strategy",
        "manual_prediction_override",
        "manual_sgn_override",
        "confidence",
        "justification_comment",
        "scenario_before",
        "scenario_after",
        "change_flag",
        "ann_magnitude",
        "ann_sgn",
        "source_context_path",
        "source_snapshot_ref",
    }
)

_MODE_NORMALIZATION = {
    "ML": "ML",
    "ML + HUMAN REVIEW": "ML + Human Review",
    "ML+HITL": "ML + Human Review",
    "ML+HUMAN REVIEW": "ML + Human Review",
}


def _normalize_mode(raw_mode: Any) -> str:
    key = str(raw_mode or "").strip().upper()
    return _MODE_NORMALIZATION.get(key, str(raw_mode or "").strip())


def _normalize_sign(raw_sign: Any) -> str | None:
    if raw_sign is None:
        return None
    sign = str(raw_sign).strip()
    if sign in {"+", "＋"}:
        return "+"
    if sign in {"-", "−", "–", "—"}:
        return "-"
    return sign or None


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def validate_review_payload(payload: Mapping[str, Any]) -> ValidationResultModel:
    errors: list[str] = []
    warnings: list[str] = []

    extra_fields = sorted(set(payload.keys()) - set(_ALLOWED_FIELDS))
    if extra_fields:
        errors.append(f"Unexpected fields: {', '.join(extra_fields)}")

    normalized: dict[str, Any] = dict(payload)
    normalized["review_date"] = str(payload.get("review_date", "")).strip()
    normalized["ticker"] = str(payload.get("ticker", "")).strip().upper()
    normalized["mode"] = _normalize_mode(payload.get("mode"))
    normalized["gui_state"] = str(payload.get("gui_state", "SHOW")).strip().upper()
    normalized["ai_consensus_sgn"] = _normalize_sign(payload.get("ai_consensus_sgn"))
    normalized["manual_sgn_override"] = _normalize_sign(
        payload.get("manual_sgn_override")
    )
    normalized["ann_sgn"] = _normalize_sign(payload.get("ann_sgn"))

    if not normalized["review_date"]:
        errors.append("review_date is required")
    else:
        try:
            datetime.fromisoformat(normalized["review_date"])
        except ValueError:
            errors.append("review_date must be ISO date")

    if not normalized["ticker"]:
        errors.append("ticker is required")

    if normalized["mode"] not in {"ML", "ML + Human Review"}:
        errors.append("mode must be ML or ML + Human Review")

    if normalized["gui_state"] not in {"EDIT", "SHOW"}:
        errors.append("gui_state must be EDIT or SHOW")

    try:
        normalized["ai_consensus_value"] = _to_float_or_none(
            payload.get("ai_consensus_value")
        )
        normalized["manual_prediction_override"] = _to_float_or_none(
            payload.get("manual_prediction_override")
        )
        normalized["ann_magnitude"] = _to_float_or_none(payload.get("ann_magnitude"))
    except (TypeError, ValueError):
        errors.append("numeric fields contain invalid values")

    confidence_raw = payload.get("confidence")
    if confidence_raw in (None, ""):
        normalized["confidence"] = None
    else:
        try:
            confidence_int = int(confidence_raw)
            normalized["confidence"] = confidence_int
            if confidence_int < 0 or confidence_int > 100:
                errors.append("confidence must be in range 0..100")
        except (TypeError, ValueError):
            errors.append("confidence must be an integer")

    comment = str(payload.get("justification_comment", "") or "").strip()
    normalized["justification_comment"] = comment
    if len(comment) > 2000:
        errors.append("justification_comment exceeds max length")

    if normalized.get("manual_sgn_override") not in {None, "+", "-"}:
        errors.append("manual_sgn_override must be '+' or '-' when present")

    if normalized.get("ai_consensus_sgn") not in {None, "+", "-"}:
        errors.append("ai_consensus_sgn must be '+' or '-' when present")

    ai_value = normalized.get("ai_consensus_value")
    manual_value = normalized.get("manual_prediction_override")
    delta_requires_comment = (
        ai_value is not None
        and manual_value is not None
        and abs(float(manual_value) - float(ai_value)) > 0.5
    )
    sign_requires_comment = (
        normalized.get("manual_sgn_override") is not None
        and normalized.get("ai_consensus_sgn") is not None
        and normalized.get("manual_sgn_override") != normalized.get("ai_consensus_sgn")
    )
    change_flag = bool(payload.get("change_flag"))
    normalized["change_flag"] = change_flag

    if (delta_requires_comment or sign_requires_comment or change_flag) and not comment:
        errors.append("justification_comment is required for material review changes")

    if normalized["gui_state"] == "SHOW" and normalized["mode"] == "ML + Human Review":
        warnings.append("Human review mode is active, but GUI state is read-only")

    ok = len(errors) == 0
    return ValidationResultModel(
        ok=ok,
        errors=tuple(errors),
        warnings=tuple(warnings),
        normalized=normalized,
    )


def save_review_payload(repo: ReviewRepository, payload: Mapping[str, Any]) -> int:
    validation = validate_review_payload(payload)
    if not validation.ok:
        joined = "; ".join(validation.errors)
        raise ValueError(f"Review payload validation failed: {joined}")
    model = ReviewPayloadModel(**validation.normalized)
    return repo.save_review_payload(model)


def export_review_payload(
    repo: ReviewRepository,
    review_id: int,
    export_format: str,
    export_scope: str,
) -> str:
    _ = export_scope
    if export_format.lower() != "json":
        raise ValueError("Only json export is supported in MVP")
    session = repo.load_review_by_id(review_id)
    if session is None:
        raise ValueError(f"Review id not found: {review_id}")
    return export_payload_json_text(session)


def load_available_review_dates(vg_db_path: Path | None = None) -> list[dict[str, Any]]:
    db_path = vg_db_path or paths.OUT_I_CALC_ML_VG_DB_PATH
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT forecast_date, round_state
            FROM rounds
            ORDER BY forecast_date DESC
            """
        ).fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        mapped = map_round_state(str(row["round_state"]))
        out.append(
            {
                "review_date": str(row["forecast_date"]),
                "raw_round_state": mapped.raw_round_state,
                "gui_state": mapped.gui_state,
                "editable": mapped.editable,
                "reason": mapped.reason,
            }
        )
    return out


def load_available_tickers() -> list[str]:
    return ["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"]


def _default_repo(review_db_path: Path | None = None) -> ReviewRepository:
    db_path = review_db_path or (paths.OUT_I_CALC_DIR / "HITL" / "HITL_review.sqlite")
    return ReviewRepository(db_path)


def load_model_comparison(
    review_date: str, ticker: str
) -> list[ModelComparisonRowModel]:
    _ = review_date
    _ = ticker
    return []


def load_reference_values(review_date: str, ticker: str) -> dict[str, Any]:
    _ = review_date
    _ = ticker
    return {}


def load_review_context(
    review_date: str,
    ticker: str,
    mode: str,
    review_db_path: Path | None = None,
) -> dict[str, Any]:
    repo = _default_repo(review_db_path)
    normalized_mode = _normalize_mode(mode)
    session = repo.load_review_payload(review_date, ticker, normalized_mode)
    if session is None:
        payload = {
            "review_date": review_date,
            "ticker": ticker,
            "mode": normalized_mode,
            "gui_state": "SHOW",
            "ai_consensus_value": None,
            "ai_consensus_sgn": None,
            "ai_consensus_strategy": "policy_selected",
            "manual_prediction_override": None,
            "manual_sgn_override": None,
            "confidence": None,
            "justification_comment": "",
            "scenario_before": None,
            "scenario_after": None,
            "change_flag": False,
            "ann_magnitude": None,
            "ann_sgn": None,
            "source_context_path": None,
            "source_snapshot_ref": None,
        }
    else:
        payload = dict(session.payload.__dict__)

    return {
        "review_date": review_date,
        "ticker": ticker,
        "mode": normalized_mode,
        "payload": payload,
        "model_comparison": load_model_comparison(review_date, ticker),
        "reference_values": load_reference_values(review_date, ticker),
    }


def load_audit_history(
    review_date: str,
    ticker: str,
    review_db_path: Path | None = None,
) -> AuditHistoryModel:
    repo = _default_repo(review_db_path)
    return repo.load_audit_history(review_date, ticker)


def load_ann_snapshot(review_date: str, ticker: str) -> ANNSnapshotModel:
    _ = review_date
    _ = ticker
    return ANNSnapshotModel(
        review_date=review_date,
        ticker=ticker,
        ann_sgn=None,
        ann_magnitude=None,
        source_label=None,
        ingested_at=None,
        stale_warning=False,
    )
