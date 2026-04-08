from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ui.services.ann_feature_store import (
    initialize_ann_feature_store,
    load_ann_feature_store_summary,
    upsert_ann_feature_records,
)


def test_initialize_ann_feature_store_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "ann_input_features.sqlite"
    initialize_ann_feature_store(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "schema_meta" in table_names
    assert "ann_feature_ingest_files" in table_names
    assert "ann_ti_inputs" in table_names
    assert "ann_pivot_inputs" in table_names
    assert "ann_hurst_inputs" in table_names
    assert "ann_tda_h1_inputs" in table_names


def test_upsert_ann_feature_records_writes_rows_and_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "ann_input_features.sqlite"
    initialize_ann_feature_store(db_path)

    records = [
        {
            "as_of_date": "2026-03-31",
            "ticker": "SPX",
            "feature_name": "RSI (14)",
            "feature_value": 54.1,
            "source_family": "ti",
            "source_file": "/tmp/TI/GSPC.csv",
            "value_status": "present",
        },
        {
            "as_of_date": "2026-03-31",
            "ticker": "SPX",
            "feature_name": "Pivot Points(Classic)",
            "feature_value": 6348.666,
            "source_family": "pivot",
            "source_file": "/tmp/PP/GSPC.csv",
            "value_status": "present",
        },
        {
            "as_of_date": "2026-03-31",
            "ticker": "SPX",
            "feature_name": "H20",
            "feature_value": 0.49,
            "source_family": "hurst",
            "source_file": "/tmp/svl/SVL_METRICS_20260331.csv",
            "value_status": "present",
        },
        {
            "as_of_date": "2026-03-31",
            "ticker": "SPX",
            "feature_name": "H1_Entropy",
            "feature_value": 2.115,
            "source_family": "tda_h1",
            "source_file": "/tmp/tda/TDA_METRICS_20260331.csv",
            "value_status": "present",
        },
    ]

    out = upsert_ann_feature_records(
        store_path=db_path,
        records=records,
        source_batch="20260331",
    )
    assert out["rows_written"] == 4

    summary = load_ann_feature_store_summary(db_path)
    assert summary["exists"] is True
    assert summary["families"]["ti"]["rows"] == 1
    assert summary["families"]["pivot"]["rows"] == 1
    assert summary["families"]["hurst"]["rows"] == 1
    assert summary["families"]["tda_h1"]["rows"] == 1
    assert summary["families"]["ti"]["latest_as_of_date"] == "2026-03-31"
