from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


def _bootstrap_sys_path() -> Path:
    here = Path(__file__).resolve()
    app_root = here.parents[1]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.config import paths


TICKERS: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest marker markdown tables from data/raw/ann into canonical SQLite store."
    )
    p.add_argument(
        "--raw-dir",
        type=str,
        default=str(paths.DATA_RAW_DIR / "ann"),
        help="Directory containing date-named marker files (YYYY-MM-DD.txt).",
    )
    p.add_argument(
        "--store-path",
        type=str,
        default=str(paths.OUT_I_CALC_DIR / "stores" / "ann_markers_store.sqlite"),
        help="SQLite path for canonical ANN marker store.",
    )
    p.add_argument(
        "--glob",
        type=str,
        default="*.txt",
        help="File glob filter under raw-dir (default: *.txt).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest files even when file hash already exists.",
    )
    return p.parse_args(list(argv) if argv is not None else None)


def marker_to_canonical(marker_raw: str) -> str:
    text = marker_raw.strip().lower().replace("<br>", " ")
    text = re.sub(r"\s+", " ", text)

    if "close" in text and "yahoo" in text:
        return "close_yahoo_finance"
    if "close" in text and "investing" in text:
        return "close_investing_com"
    if "close" in text and "anchor" in text:
        return "close_anchor_mark"
    if "+3-day" in text or "close real" in text:
        return "close_real_tplus3"
    if text == "rd":
        return "RD"
    if text == "85220":
        return "85220"
    if text in {"mich", "micho"} or "mich" in text:
        return "MICHO"

    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return slug or "unknown_marker"


def parse_decimal(raw: str) -> Optional[float]:
    value = raw.strip()
    if not value:
        return None
    value = value.replace(",", "")
    return float(value)


def normalize_lines(raw_text: str) -> List[str]:
    return [line.rstrip("\n") for line in raw_text.splitlines() if line.strip()]


def parse_marker_rows(lines: Iterable[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if not parts:
            continue
        first = parts[0].lower()
        if first.startswith("ticker"):
            continue
        if first.startswith(":----"):
            continue
        rows.append(parts)
    return rows


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ann_marker_ingest_files (
            ingest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            note TEXT,
            UNIQUE(file_hash),
            UNIQUE(file_path, as_of_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ann_marker_values (
            as_of_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            marker_name_raw TEXT NOT NULL,
            marker_name_canonical TEXT NOT NULL,
            marker_value_decimal REAL,
            value_status TEXT NOT NULL,
            source_file TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (as_of_date, ticker, marker_name_canonical)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ann_marker_values_date_ticker
        ON ann_marker_values(as_of_date, ticker)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


def ingest_file(
    conn: sqlite3.Connection, file_path: Path, *, force: bool
) -> Dict[str, object]:
    as_of_date = file_path.stem
    if not DATE_RE.match(as_of_date):
        return {
            "file": str(file_path),
            "as_of_date": as_of_date,
            "status": "skipped_invalid_name",
            "rows": 0,
        }

    content = file_path.read_text(encoding="utf-8")
    norm_lines = normalize_lines(content)
    normalized = as_of_date + "\n" + "\n".join(norm_lines) + "\n"
    file_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if not force:
        existing = conn.execute(
            "SELECT ingest_id FROM ann_marker_ingest_files WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
        if existing:
            return {
                "file": str(file_path),
                "as_of_date": as_of_date,
                "status": "skipped_existing",
                "rows": 0,
            }

    parsed_rows = parse_marker_rows(norm_lines)
    written = 0

    for row in parsed_rows:
        if len(row) < 7:
            continue
        marker_raw = row[0]
        marker_canonical = marker_to_canonical(marker_raw)
        values = row[1:7]

        for ticker, raw in zip(TICKERS, values):
            value = parse_decimal(raw)
            if value is None:
                status = (
                    "pending_tplus3"
                    if marker_canonical == "close_real_tplus3"
                    else "missing"
                )
            else:
                status = "present"

            conn.execute(
                """
                INSERT INTO ann_marker_values (
                    as_of_date,
                    ticker,
                    marker_name_raw,
                    marker_name_canonical,
                    marker_value_decimal,
                    value_status,
                    source_file,
                    file_hash,
                    ingested_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(as_of_date, ticker, marker_name_canonical) DO UPDATE SET
                    marker_name_raw = excluded.marker_name_raw,
                    marker_value_decimal = excluded.marker_value_decimal,
                    value_status = excluded.value_status,
                    source_file = excluded.source_file,
                    file_hash = excluded.file_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    as_of_date,
                    ticker,
                    marker_raw,
                    marker_canonical,
                    value,
                    status,
                    str(file_path),
                    file_hash,
                    now,
                    now,
                ),
            )
            written += 1

    conn.execute(
        """
        INSERT INTO ann_marker_ingest_files (
            file_path,
            as_of_date,
            file_hash,
            row_count,
            status,
            ingested_at,
            note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_path, as_of_date) DO UPDATE SET
            file_hash = excluded.file_hash,
            row_count = excluded.row_count,
            status = excluded.status,
            ingested_at = excluded.ingested_at,
            note = excluded.note
        """,
        (
            str(file_path),
            as_of_date,
            file_hash,
            written,
            "ingested",
            now,
            "source=markdown_table",
        ),
    )

    return {
        "file": str(file_path),
        "as_of_date": as_of_date,
        "status": "ingested",
        "rows": written,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    paths.ensure_directories()

    raw_dir = Path(args.raw_dir).resolve()
    if not raw_dir.exists() or not raw_dir.is_dir():
        raise SystemExit(f"raw-dir does not exist or is not directory: {raw_dir}")

    store_path = Path(args.store_path).resolve()
    store_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob(args.glob))
    if not files:
        print(f"[ann_markers_ingest] No files matched {args.glob} in {raw_dir}")
        return 0

    summaries: List[Dict[str, object]] = []
    with sqlite3.connect(store_path) as conn:
        ensure_schema(conn)
        for fp in files:
            summaries.append(ingest_file(conn, fp, force=bool(args.force)))

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.execute(
            """
            INSERT INTO schema_meta(meta_key, meta_value, updated_at)
            VALUES ('store_name', 'ann_markers_store', ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value = excluded.meta_value,
                updated_at = excluded.updated_at
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO schema_meta(meta_key, meta_value, updated_at)
            VALUES ('schema_version', 'v1', ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value = excluded.meta_value,
                updated_at = excluded.updated_at
            """,
            (now,),
        )

    ingested = [s for s in summaries if s["status"] == "ingested"]
    skipped = [s for s in summaries if str(s["status"]).startswith("skipped")]
    total_rows = 0
    for s in summaries:
        raw_rows = s.get("rows", 0)
        if isinstance(raw_rows, (int, float)):
            total_rows += int(raw_rows)
        elif isinstance(raw_rows, str) and raw_rows.strip():
            total_rows += int(raw_rows)

    print(f"[ann_markers_ingest] store={store_path}")
    print(
        f"[ann_markers_ingest] files={len(summaries)} ingested={len(ingested)} skipped={len(skipped)}"
    )
    print(f"[ann_markers_ingest] rows_written={total_rows}")
    for s in summaries:
        print(f"  {s['as_of_date']}: {s['status']} rows={s['rows']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
