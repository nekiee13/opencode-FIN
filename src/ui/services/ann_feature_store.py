from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANN_FEATURE_STORE_SCHEMA_VERSION = "ann-input-features-v1"

FAMILY_TABLES: dict[str, str] = {
    "ti": "ann_ti_inputs",
    "pivot": "ann_pivot_inputs",
    "hurst": "ann_hurst_inputs",
    "tda_h1": "ann_tda_h1_inputs",
}


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _connect(store_path: Path) -> sqlite3.Connection:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(store_path))


def initialize_ann_feature_store(store_path: Path) -> None:
    now = _now_iso()
    conn = _connect(store_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ann_feature_ingest_files (
                ingest_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                source_family TEXT NOT NULL,
                source_batch TEXT NOT NULL,
                rows_written INTEGER NOT NULL,
                status TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                note TEXT,
                UNIQUE(file_path, source_family, source_batch)
            );

            CREATE TABLE IF NOT EXISTS ann_ti_inputs (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL,
                value_status TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_batch TEXT NOT NULL,
                loaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (as_of_date, ticker, feature_name)
            );

            CREATE TABLE IF NOT EXISTS ann_pivot_inputs (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL,
                value_status TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_batch TEXT NOT NULL,
                loaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (as_of_date, ticker, feature_name)
            );

            CREATE TABLE IF NOT EXISTS ann_hurst_inputs (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL,
                value_status TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_batch TEXT NOT NULL,
                loaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (as_of_date, ticker, feature_name)
            );

            CREATE TABLE IF NOT EXISTS ann_tda_h1_inputs (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL,
                value_status TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_batch TEXT NOT NULL,
                loaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (as_of_date, ticker, feature_name)
            );
            """
        )

        for table_name in FAMILY_TABLES.values():
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_date_ticker ON {table_name}(as_of_date, ticker)"
            )

        conn.execute(
            """
            INSERT INTO schema_meta(meta_key, meta_value, updated_at)
            VALUES('schema_version', ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value=excluded.meta_value,
                updated_at=excluded.updated_at
            """,
            (ANN_FEATURE_STORE_SCHEMA_VERSION, now),
        )
        conn.commit()
    finally:
        conn.close()


def _upsert_one(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    as_of_date: str,
    ticker: str,
    feature_name: str,
    feature_value: float | None,
    value_status: str,
    source_file: str,
    source_batch: str,
    now: str,
) -> None:
    conn.execute(
        f"""
        INSERT INTO {table_name} (
            as_of_date,
            ticker,
            feature_name,
            feature_value,
            value_status,
            source_file,
            source_batch,
            loaded_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of_date, ticker, feature_name) DO UPDATE SET
            feature_value=excluded.feature_value,
            value_status=excluded.value_status,
            source_file=excluded.source_file,
            source_batch=excluded.source_batch,
            updated_at=excluded.updated_at
        """,
        (
            as_of_date,
            ticker,
            feature_name,
            feature_value,
            value_status,
            source_file,
            source_batch,
            now,
            now,
        ),
    )


def upsert_ann_feature_records(
    *,
    store_path: Path,
    records: list[dict[str, Any]],
    source_batch: str,
) -> dict[str, Any]:
    initialize_ann_feature_store(store_path)
    now = _now_iso()
    written = 0
    by_family: dict[str, int] = {k: 0 for k in FAMILY_TABLES}

    conn = _connect(store_path)
    try:
        for item in records:
            source_family = str(item.get("source_family") or "").strip()
            table_name = FAMILY_TABLES.get(source_family)
            if not table_name:
                continue

            as_of_date = str(item.get("as_of_date") or "").strip()
            ticker = str(item.get("ticker") or "").strip().upper()
            feature_name = str(item.get("feature_name") or "").strip()
            value_status = str(item.get("value_status") or "").strip() or "missing"
            source_file = str(item.get("source_file") or "").strip()
            raw_value = item.get("feature_value")
            feature_value: float | None = None
            if isinstance(raw_value, (int, float)):
                feature_value = float(raw_value)

            if not as_of_date or not ticker or not feature_name:
                continue

            _upsert_one(
                conn,
                table_name=table_name,
                as_of_date=as_of_date,
                ticker=ticker,
                feature_name=feature_name,
                feature_value=feature_value,
                value_status=value_status,
                source_file=source_file,
                source_batch=str(source_batch),
                now=now,
            )
            written += 1
            by_family[source_family] = int(by_family.get(source_family, 0)) + 1
        conn.commit()
    finally:
        conn.close()

    return {
        "store_path": str(store_path),
        "rows_written": int(written),
        "rows_by_family": by_family,
    }


def record_ingest_file(
    *,
    store_path: Path,
    file_path: str,
    source_family: str,
    source_batch: str,
    rows_written: int,
    status: str,
    note: str = "",
) -> None:
    initialize_ann_feature_store(store_path)
    conn = _connect(store_path)
    try:
        conn.execute(
            """
            INSERT INTO ann_feature_ingest_files(
                file_path,
                source_family,
                source_batch,
                rows_written,
                status,
                ingested_at,
                note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path, source_family, source_batch) DO UPDATE SET
                rows_written=excluded.rows_written,
                status=excluded.status,
                ingested_at=excluded.ingested_at,
                note=excluded.note
            """,
            (
                str(file_path),
                str(source_family),
                str(source_batch),
                int(rows_written),
                str(status),
                _now_iso(),
                str(note),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_ann_feature_store_summary(store_path: Path) -> dict[str, Any]:
    if not store_path.exists():
        return {
            "exists": False,
            "store_path": str(store_path),
            "families": {
                family: {"rows": 0, "latest_as_of_date": None}
                for family in FAMILY_TABLES
            },
        }

    conn = _connect(store_path)
    try:
        families: dict[str, dict[str, Any]] = {}
        for family, table_name in FAMILY_TABLES.items():
            rows = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            latest = conn.execute(
                f"SELECT MAX(as_of_date) FROM {table_name}"
            ).fetchone()
            families[family] = {
                "rows": int(rows[0]) if rows else 0,
                "latest_as_of_date": str(latest[0]) if latest and latest[0] else None,
            }
    finally:
        conn.close()

    return {
        "exists": True,
        "store_path": str(store_path),
        "families": families,
    }


def load_ann_feature_date_coverage(
    store_path: Path,
    *,
    as_of_date: str,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    target_date = str(as_of_date or "").strip()
    expected = [str(x).strip().upper() for x in list(tickers or []) if str(x).strip()]
    expected_set = set(expected)

    out: dict[str, Any] = {
        "exists": bool(store_path.exists()),
        "store_path": str(store_path),
        "as_of_date": target_date,
        "expected_tickers": expected,
        "families": {},
        "complete": False,
    }
    if not store_path.exists() or not target_date or not expected:
        return out

    conn = _connect(store_path)
    try:
        families: dict[str, dict[str, Any]] = {}
        for family, table_name in FAMILY_TABLES.items():
            rows = conn.execute(
                f"""
                SELECT DISTINCT ticker
                FROM {table_name}
                WHERE as_of_date = ? AND value_status = 'present'
                """,
                (target_date,),
            ).fetchall()
            present_set = {
                str(row[0]).strip().upper()
                for row in rows
                if row and str(row[0]).strip()
            }
            present = sorted(expected_set.intersection(present_set))
            missing = sorted(expected_set.difference(present_set))
            families[family] = {
                "present_tickers": present,
                "missing_tickers": missing,
                "present_count": int(len(present)),
                "expected_count": int(len(expected_set)),
                "complete": len(missing) == 0,
            }
    finally:
        conn.close()

    out["families"] = families
    out["complete"] = bool(
        families and all(bool(item.get("complete")) for item in families.values())
    )
    return out


__all__ = [
    "ANN_FEATURE_STORE_SCHEMA_VERSION",
    "FAMILY_TABLES",
    "initialize_ann_feature_store",
    "upsert_ann_feature_records",
    "record_ingest_file",
    "load_ann_feature_store_summary",
    "load_ann_feature_date_coverage",
]
