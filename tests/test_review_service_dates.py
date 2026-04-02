from __future__ import annotations

from pathlib import Path

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
