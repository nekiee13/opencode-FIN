from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.review.audit import build_field_diffs
from src.review.models import (
    AuditHistoryModel,
    ReviewEventModel,
    ReviewPayloadModel,
    ReviewSessionModel,
)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


_TRACKED_DIFF_FIELDS: tuple[str, ...] = (
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
)


class ReviewRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                  review_id INTEGER PRIMARY KEY,
                  round_id TEXT,
                  review_date TEXT NOT NULL,
                  ticker TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  gui_state TEXT NOT NULL,
                  ai_consensus_value REAL,
                  ai_consensus_sgn TEXT,
                  ai_consensus_strategy TEXT,
                  manual_prediction_override REAL,
                  manual_sgn_override TEXT,
                  confidence INTEGER,
                  justification_comment TEXT,
                  scenario_before TEXT,
                  scenario_after TEXT,
                  change_flag INTEGER NOT NULL DEFAULT 0,
                  ratio_star_before REAL,
                  ratio_star_after REAL,
                  rd_star_before REAL,
                  rd_star_after REAL,
                  ann_magnitude REAL,
                  ann_sgn TEXT,
                  source_context_path TEXT,
                  source_snapshot_ref TEXT,
                  save_status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(review_date, ticker, mode)
                );

                CREATE TABLE IF NOT EXISTS review_events (
                  event_id INTEGER PRIMARY KEY,
                  review_id INTEGER NOT NULL,
                  event_type TEXT NOT NULL,
                  field_name TEXT,
                  old_value TEXT,
                  new_value TEXT,
                  event_status TEXT NOT NULL,
                  error_text TEXT,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(review_id) REFERENCES review_sessions(review_id)
                );

                CREATE INDEX IF NOT EXISTS idx_review_sessions_date_ticker
                ON review_sessions(review_date, ticker);

                CREATE INDEX IF NOT EXISTS idx_review_events_review_id
                ON review_events(review_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def load_review_payload(
        self, review_date: str, ticker: str, mode: str
    ) -> ReviewSessionModel | None:
        self.initialize_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM review_sessions
                WHERE review_date = ? AND ticker = ? AND mode = ?
                LIMIT 1
                """,
                (review_date, ticker, mode),
            ).fetchone()
            if row is None:
                return None
            return _session_from_row(row)
        finally:
            conn.close()

    def load_review_by_id(self, review_id: int) -> ReviewSessionModel | None:
        self.initialize_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE review_id = ? LIMIT 1",
                (int(review_id),),
            ).fetchone()
            if row is None:
                return None
            return _session_from_row(row)
        finally:
            conn.close()

    def save_review_payload(self, payload: ReviewPayloadModel) -> int:
        self.initialize_schema()
        now = _utc_now()
        existing = self.load_review_payload(
            payload.review_date, payload.ticker, payload.mode
        )
        existing_data = asdict(existing.payload) if existing else None
        incoming_data = asdict(payload)
        diff_rows = build_field_diffs(
            existing_data, incoming_data, _TRACKED_DIFF_FIELDS
        )
        created_at = existing.created_at if existing else now

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO review_sessions (
                  round_id, review_date, ticker, mode, gui_state,
                  ai_consensus_value, ai_consensus_sgn, ai_consensus_strategy,
                  manual_prediction_override, manual_sgn_override,
                  confidence, justification_comment,
                  scenario_before, scenario_after, change_flag,
                  ann_magnitude, ann_sgn,
                  source_context_path, source_snapshot_ref,
                  save_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_date, ticker, mode) DO UPDATE SET
                  round_id=excluded.round_id,
                  gui_state=excluded.gui_state,
                  ai_consensus_value=excluded.ai_consensus_value,
                  ai_consensus_sgn=excluded.ai_consensus_sgn,
                  ai_consensus_strategy=excluded.ai_consensus_strategy,
                  manual_prediction_override=excluded.manual_prediction_override,
                  manual_sgn_override=excluded.manual_sgn_override,
                  confidence=excluded.confidence,
                  justification_comment=excluded.justification_comment,
                  scenario_before=excluded.scenario_before,
                  scenario_after=excluded.scenario_after,
                  change_flag=excluded.change_flag,
                  ann_magnitude=excluded.ann_magnitude,
                  ann_sgn=excluded.ann_sgn,
                  source_context_path=excluded.source_context_path,
                  source_snapshot_ref=excluded.source_snapshot_ref,
                  save_status=excluded.save_status,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at
                """,
                (
                    payload.round_id,
                    payload.review_date,
                    payload.ticker,
                    payload.mode,
                    payload.gui_state,
                    payload.ai_consensus_value,
                    payload.ai_consensus_sgn,
                    payload.ai_consensus_strategy,
                    payload.manual_prediction_override,
                    payload.manual_sgn_override,
                    payload.confidence,
                    payload.justification_comment,
                    payload.scenario_before,
                    payload.scenario_after,
                    1 if payload.change_flag else 0,
                    payload.ann_magnitude,
                    payload.ann_sgn,
                    payload.source_context_path,
                    payload.source_snapshot_ref,
                    "SAVED",
                    created_at,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT review_id
                FROM review_sessions
                WHERE review_date = ? AND ticker = ? AND mode = ?
                LIMIT 1
                """,
                (payload.review_date, payload.ticker, payload.mode),
            ).fetchone()
            assert row is not None
            review_id = int(row["review_id"])

            conn.execute(
                """
                INSERT INTO review_events (
                  review_id, event_type, field_name, old_value, new_value,
                  event_status, error_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (review_id, "SAVE", None, None, None, "OK", None, now),
            )

            for field_name, old_value, new_value in diff_rows:
                conn.execute(
                    """
                    INSERT INTO review_events (
                      review_id, event_type, field_name, old_value, new_value,
                      event_status, error_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        "FIELD_DIFF",
                        field_name,
                        old_value,
                        new_value,
                        "OK",
                        None,
                        now,
                    ),
                )
            conn.commit()
            return review_id
        finally:
            conn.close()

    def load_audit_history(self, review_date: str, ticker: str) -> AuditHistoryModel:
        self.initialize_schema()
        conn = self._connect()
        try:
            session_row = conn.execute(
                """
                SELECT review_id
                FROM review_sessions
                WHERE review_date = ? AND ticker = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (review_date, ticker),
            ).fetchone()
            if session_row is None:
                return AuditHistoryModel(
                    review_date=review_date, ticker=ticker, events=tuple()
                )

            review_id = int(session_row["review_id"])
            rows = conn.execute(
                """
                SELECT *
                FROM review_events
                WHERE review_id = ?
                ORDER BY event_id ASC
                """,
                (review_id,),
            ).fetchall()
            events = tuple(_event_from_row(row) for row in rows)
            return AuditHistoryModel(
                review_date=review_date, ticker=ticker, events=events
            )
        finally:
            conn.close()


def _payload_from_row(row: sqlite3.Row) -> ReviewPayloadModel:
    return ReviewPayloadModel(
        round_id=row["round_id"],
        review_date=row["review_date"],
        ticker=row["ticker"],
        mode=row["mode"],
        gui_state=row["gui_state"],
        ai_consensus_value=row["ai_consensus_value"],
        ai_consensus_sgn=row["ai_consensus_sgn"],
        ai_consensus_strategy=row["ai_consensus_strategy"],
        manual_prediction_override=row["manual_prediction_override"],
        manual_sgn_override=row["manual_sgn_override"],
        confidence=row["confidence"],
        justification_comment=row["justification_comment"],
        scenario_before=row["scenario_before"],
        scenario_after=row["scenario_after"],
        change_flag=bool(row["change_flag"]),
        ann_magnitude=row["ann_magnitude"],
        ann_sgn=row["ann_sgn"],
        source_context_path=row["source_context_path"],
        source_snapshot_ref=row["source_snapshot_ref"],
    )


def _session_from_row(row: sqlite3.Row) -> ReviewSessionModel:
    return ReviewSessionModel(
        review_id=int(row["review_id"]),
        payload=_payload_from_row(row),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        save_status=str(row["save_status"]),
    )


def _event_from_row(row: sqlite3.Row) -> ReviewEventModel:
    return ReviewEventModel(
        event_id=int(row["event_id"]),
        review_id=int(row["review_id"]),
        event_type=str(row["event_type"]),
        field_name=row["field_name"],
        old_value=row["old_value"],
        new_value=row["new_value"],
        event_status=str(row["event_status"]),
        error_text=row["error_text"],
        created_at=str(row["created_at"]),
    )
