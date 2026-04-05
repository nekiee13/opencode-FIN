from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ui.services.ann_ops import load_ann_store_summary


def test_load_ann_store_summary_missing_store(tmp_path: Path) -> None:
    out = load_ann_store_summary(tmp_path / "missing.sqlite")
    assert out["exists"] is False
    assert out["rows"] == 0


def test_load_ann_store_summary_reads_latest_date(tmp_path: Path) -> None:
    db_path = tmp_path / "ann_markers_store.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ann_marker_values (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                marker_name_canonical TEXT NOT NULL,
                marker_value_decimal REAL,
                PRIMARY KEY (as_of_date, ticker, marker_name_canonical)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ann_marker_values(as_of_date, ticker, marker_name_canonical, marker_value_decimal)
            VALUES ('2026-03-24', 'TNX', 'RD', 4.33)
            """
        )
        conn.execute(
            """
            INSERT INTO ann_marker_values(as_of_date, ticker, marker_name_canonical, marker_value_decimal)
            VALUES ('2026-03-31', 'TNX', 'RD', 4.34)
            """
        )
        conn.commit()
    finally:
        conn.close()

    out = load_ann_store_summary(db_path)
    assert out["exists"] is True
    assert out["rows"] == 2
    assert out["latest_as_of_date"] == "2026-03-31"
