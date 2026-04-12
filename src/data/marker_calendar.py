from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from src.config import paths

TICKER_ORDER: tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
MARKER_FILES: tuple[str, ...] = ("rd.csv", "85220.csv", "oraclum.csv")
_DATE_FORMATS: tuple[str, ...] = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d")


@dataclass(frozen=True)
class DateWarning:
    allowable_date: str
    ticker: str
    expected_plus3: str
    used_date: str
    fallback_used: str


def parse_marker_date(raw: str) -> date | None:
    text = str(raw or "").strip().strip('"')
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_marker_date(day: date) -> str:
    return day.strftime("%b %d, %Y")


def _marker_dates_for_file(path: Path) -> set[date]:
    out: set[date] = set()
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            parsed = parse_marker_date(str(row.get("Date") or ""))
            if parsed is not None:
                out.add(parsed)
    return out


def validate_marker_tuesdays(markers_dir: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for marker_file in MARKER_FILES:
        path = markers_dir / marker_file
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw = str(row.get("Date") or "")
                parsed = parse_marker_date(raw)
                if parsed is None:
                    issues.append(
                        {
                            "marker_file": marker_file,
                            "raw_date": raw,
                            "iso_date": "",
                            "weekday": "unparsed",
                        }
                    )
                    continue
                if parsed.weekday() != 1:
                    issues.append(
                        {
                            "marker_file": marker_file,
                            "raw_date": raw,
                            "iso_date": parsed.isoformat(),
                            "weekday": parsed.strftime("%A"),
                        }
                    )
    return issues


def build_allowable_dates(markers_dir: Path) -> list[date]:
    sets: list[set[date]] = []
    for marker_file in MARKER_FILES:
        path = markers_dir / marker_file
        sets.append(_marker_dates_for_file(path))
    if not sets:
        return []
    intersection = set.intersection(*sets)
    return sorted(intersection, reverse=True)


def write_dates_csv(dates: Sequence[date], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date"])
        for day in dates:
            writer.writerow([format_marker_date(day)])
    return output_path


def _ticker_symbol_for_file(ticker: str) -> str:
    return "GSPC" if str(ticker).upper() == "SPX" else str(ticker).upper()


def _load_ticker_close_map(tickers_dir: Path, ticker: str) -> dict[date, float]:
    out: dict[date, float] = {}
    symbol = _ticker_symbol_for_file(ticker)
    csv_path = tickers_dir / f"{symbol}_data.csv"
    if not csv_path.exists():
        return out
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            parsed = parse_marker_date(str(row.get("Date") or ""))
            if parsed is None:
                continue
            raw_close = str(row.get("Close") or "").strip().replace(",", "")
            try:
                out[parsed] = float(raw_close)
            except ValueError:
                continue
    return out


def build_tplus3_rows(
    *,
    allowable_dates: Sequence[date],
    tickers_dir: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    close_maps = {
        ticker: _load_ticker_close_map(tickers_dir, ticker) for ticker in TICKER_ORDER
    }
    rows: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for anchor_date in allowable_dates:
        expected_plus3 = anchor_date + timedelta(days=3)
        fallback_plus2 = anchor_date + timedelta(days=2)
        row: dict[str, str] = {"Date": format_marker_date(anchor_date)}
        for ticker in TICKER_ORDER:
            closes = close_maps.get(ticker, {})
            value: float | None = None
            used_date = ""
            fallback_used = "+3"
            if expected_plus3 in closes:
                value = closes[expected_plus3]
                used_date = expected_plus3.isoformat()
            elif fallback_plus2 in closes:
                value = closes[fallback_plus2]
                used_date = fallback_plus2.isoformat()
                fallback_used = "+2"
            else:
                fallback_used = "missing"
            row[ticker] = "" if value is None else f"{value:.4f}"
            if fallback_used != "+3":
                warnings.append(
                    {
                        "allowable_date": anchor_date.isoformat(),
                        "ticker": ticker,
                        "expected_plus3": expected_plus3.isoformat(),
                        "used_date": used_date,
                        "fallback_used": fallback_used,
                    }
                )
        rows.append(row)
    return rows, warnings


def write_3_days_csv(rows: Sequence[dict[str, str]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Date", *TICKER_ORDER])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: str(row.get(key) or "") for key in ["Date", *TICKER_ORDER]}
            )
    return output_path


def write_dates_warnings(warnings: Sequence[dict[str, str]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if not warnings:
        lines.append("No date warnings.")
    else:
        lines.append("Allowable dates with +3 lookup gaps:\n")
        for item in warnings:
            allow = str(item.get("allowable_date") or "")
            ticker = str(item.get("ticker") or "")
            plus3 = str(item.get("expected_plus3") or "")
            used = str(item.get("used_date") or "")
            fb = str(item.get("fallback_used") or "")
            if fb == "+2":
                lines.append(
                    f"- {allow} {ticker}: +3({plus3}) missing; used +2({used})."
                )
            else:
                lines.append(
                    f"- {allow} {ticker}: +3({plus3}) missing and +2 unavailable."
                )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def generate_marker_calendar_artifacts(
    *,
    markers_dir: Path | None = None,
    tickers_dir: Path | None = None,
) -> dict[str, object]:
    use_markers = (markers_dir or (paths.DATA_RAW_DIR / "markers")).resolve()
    use_tickers = (tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    tuesday_issues = validate_marker_tuesdays(use_markers)
    allowable_dates = build_allowable_dates(use_markers)
    rows, warnings = build_tplus3_rows(
        allowable_dates=allowable_dates,
        tickers_dir=use_tickers,
    )

    dates_csv = write_dates_csv(allowable_dates, use_markers / "Dates.csv")
    three_days_csv = write_3_days_csv(rows, use_markers / "3_days.csv")
    warn_txt = write_dates_warnings(warnings, use_markers / "dates_warnings.txt")
    return {
        "markers_dir": str(use_markers),
        "tickers_dir": str(use_tickers),
        "dates_csv": str(dates_csv),
        "three_days_csv": str(three_days_csv),
        "warnings_txt": str(warn_txt),
        "allowable_count": len(allowable_dates),
        "warning_count": len(warnings),
        "tuesday_issue_count": len(tuesday_issues),
        "tuesday_issues": tuesday_issues,
    }


__all__ = [
    "TICKER_ORDER",
    "MARKER_FILES",
    "parse_marker_date",
    "format_marker_date",
    "validate_marker_tuesdays",
    "build_allowable_dates",
    "write_dates_csv",
    "build_tplus3_rows",
    "write_3_days_csv",
    "write_dates_warnings",
    "generate_marker_calendar_artifacts",
]
