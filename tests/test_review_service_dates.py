from __future__ import annotations

from pathlib import Path
import sqlite3

from src.config import paths
from src.review.service import load_available_review_dates


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_available_review_dates_falls_back_to_marker_csv_dates(
    tmp_path: Path, monkeypatch
) -> None:
    vg_db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"
    raw_dir = tmp_path / "data" / "raw"
    markers_dir = raw_dir / "markers"
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX",
                '"Mar 24, 2026",4.38',
                '"Mar 31, 2026",4.29',
                '"Mar 17, 2026",4.24',
            ]
        )
        + "\n",
    )
    _write(
        markers_dir / "rd.csv",
        "\n".join(
            [
                "Date,TNX",
                '"Mar 24, 2026",4.33',
                '"Apr 07, 2026",4.41',
            ]
        )
        + "\n",
    )

    monkeypatch.setattr(paths, "DATA_RAW_DIR", raw_dir)

    out = load_available_review_dates(vg_db_path=vg_db_path)

    assert [item["review_date"] for item in out] == [
        "2026-04-07",
        "2026-03-31",
        "2026-03-24",
        "2026-03-17",
    ]
    assert all(item["raw_round_state"] == "MARKER_DATE" for item in out)


def test_load_available_review_dates_prefers_marker_calendar_when_db_exists(
    tmp_path: Path, monkeypatch
) -> None:
    vg_db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"
    raw_dir = tmp_path / "data" / "raw"
    markers_dir = raw_dir / "markers"
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX",
                '"Mar 24, 2026",4.38',
                '"Mar 31, 2026",4.29',
            ]
        )
        + "\n",
    )

    vg_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(vg_db_path))
    try:
        conn.execute(
            """
            CREATE TABLE rounds (
                forecast_date TEXT PRIMARY KEY,
                round_id TEXT NOT NULL UNIQUE,
                round_state TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO rounds(forecast_date, round_id, round_state)
            VALUES ('2026-03-24', '26-1-09', 'FINAL_TPLUS3')
            """
        )
        conn.execute(
            """
            INSERT INTO rounds(forecast_date, round_id, round_state)
            VALUES ('2026-02-27', '26-1-11', 'FINAL_TPLUS3')
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(paths, "DATA_RAW_DIR", raw_dir)

    out = load_available_review_dates(vg_db_path=vg_db_path)

    assert [item["review_date"] for item in out] == [
        "2026-03-31",
        "2026-03-24",
    ]
    assert out[1]["raw_round_state"] == "FINAL_TPLUS3"
    assert out[1]["gui_state"] == "SHOW"
