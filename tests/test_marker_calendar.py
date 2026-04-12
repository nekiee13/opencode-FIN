from __future__ import annotations

from datetime import date
from pathlib import Path

from src.data.marker_calendar import (
    TICKER_ORDER,
    build_allowable_dates,
    build_tplus3_rows,
    validate_marker_tuesdays,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_validate_marker_tuesdays_reports_non_tuesday_rows(tmp_path: Path) -> None:
    markers_dir = tmp_path / "markers"
    _write(
        markers_dir / "rd.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
                '"Apr 01, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )
    _write(
        markers_dir / "85220.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )

    issues = validate_marker_tuesdays(markers_dir)
    assert len(issues) == 1
    assert issues[0]["marker_file"] == "rd.csv"
    assert issues[0]["iso_date"] == "2026-04-01"
    assert issues[0]["weekday"] == "Wednesday"


def test_build_allowable_dates_uses_intersection_of_marker_files(
    tmp_path: Path,
) -> None:
    markers_dir = tmp_path / "markers"
    _write(
        markers_dir / "rd.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
                '"Mar 24, 2026",4,1,1,1,1,1',
                '"Mar 17, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )
    _write(
        markers_dir / "85220.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
                '"Mar 24, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 31, 2026",4,1,1,1,1,1',
                '"Mar 24, 2026",4,1,1,1,1,1',
                '"Mar 10, 2026",4,1,1,1,1,1',
            ]
        )
        + "\n",
    )

    out = build_allowable_dates(markers_dir)
    assert out == [date(2026, 3, 31), date(2026, 3, 24)]


def test_build_tplus3_rows_uses_plus2_fallback_and_records_warning(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "tickers"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Tue 2026-03-31 => +3 is Friday 2026-04-03 (missing); +2 is 2026-04-02 (present)
    date_row = '"Apr 02, 2026",10,10,10,100.25,100.25,0\n'
    for ticker in TICKER_ORDER:
        symbol = "GSPC" if ticker == "SPX" else ticker
        _write(
            raw_dir / f"{symbol}_data.csv",
            "Date,Open,High,Low,Close,Adj Close,Volume\n" + date_row,
        )

    rows, warnings = build_tplus3_rows(
        allowable_dates=[date(2026, 3, 31)],
        tickers_dir=raw_dir,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Date"] == "Mar 31, 2026"
    for ticker in TICKER_ORDER:
        assert row[ticker] == "100.2500"

    assert len(warnings) == len(TICKER_ORDER)
    assert all(w["fallback_used"] == "+2" for w in warnings)
    assert all(w["allowable_date"] == "2026-03-31" for w in warnings)
