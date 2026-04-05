from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.pipeline_runner import TICKER_ORDER
from src.ui.services.run_registry import latest_run_for_date
from src.ui.services.vg_loader import list_violet_forecast_dates, suggest_forecast_date

CORE_STAGES: tuple[str, ...] = ("svl_export", "tda_export", "make_fh3_table")
_PREFIX_MAP: dict[str, str] = {"SPX": "GSPC"}


def _parse_date(raw: str) -> datetime | None:
    value = str(raw or "").strip().strip('"')
    if not value:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _date_key(row: dict[str, str]) -> str | None:
    for key in row.keys():
        normalized = str(key or "").strip().lstrip("\ufeff").lower()
        if normalized == "date":
            return key
    return None


def _resolve_ticker_csv(raw_tickers_dir: Path, ticker: str) -> Path | None:
    prefix = _PREFIX_MAP.get(ticker, ticker)
    primary = (raw_tickers_dir / f"{prefix}_data.csv").resolve()
    if primary.exists():
        return primary
    legacy = (raw_tickers_dir.parent / f"{prefix}_data.csv").resolve()
    if legacy.exists():
        return legacy
    return None


def _has_data_by_date(csv_path: Path, selected_date: str) -> bool:
    cutoff = _parse_date(selected_date)
    if cutoff is None:
        return False
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = _date_key(row)
            d = _parse_date(str(row.get(key, "") if key else ""))
            if d is not None and d <= cutoff:
                return True
    return False


def _core_success_for_all_tickers(run_payload: dict[str, Any]) -> bool:
    stages = list(run_payload.get("stages", []))
    success_set = {
        (str(item.get("ticker") or ""), str(item.get("stage") or ""))
        for item in stages
        if str(item.get("status") or "") == "success"
    }
    for ticker in TICKER_ORDER:
        for stage_name in CORE_STAGES:
            if (ticker, stage_name) not in success_set:
                return False
    return True


def _first_failed_log_id(run_payload: dict[str, Any]) -> str | None:
    for item in list(run_payload.get("stages", [])):
        if str(item.get("status") or "") == "failed":
            value = str(item.get("log_id") or "").strip()
            if value:
                return value
    return None


def compute_round_status(
    *,
    selected_date: str,
    raw_tickers_dir: Path | None = None,
    runs_root: Path | None = None,
    vg_db_path: Path | None = None,
) -> dict[str, Any]:
    use_dir = (raw_tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    missing_tickers: list[str] = []
    for ticker in TICKER_ORDER:
        csv_path = _resolve_ticker_csv(use_dir, ticker)
        if csv_path is None:
            missing_tickers.append(ticker)
            continue
        if not _has_data_by_date(csv_path, selected_date):
            missing_tickers.append(ticker)

    latest = latest_run_for_date(selected_date, root_dir=runs_root)
    if latest is not None and str(latest.get("status") or "") == "failed":
        log_id = _first_failed_log_id(latest)
        return {
            "status": "VIOLET",
            "reason": "ML calculation error detected for selected round.",
            "index_code": "IDX_CALC_ERROR",
            "log_id": log_id,
            "missing_tickers": missing_tickers,
        }

    if missing_tickers:
        return {
            "status": "RED",
            "reason": "ML data missing for one or more required tickers.",
            "index_code": "IDX_DATA_MISSING",
            "log_id": None,
            "missing_tickers": missing_tickers,
        }

    if latest is not None and str(latest.get("status") or "") == "success":
        if _core_success_for_all_tickers(latest):
            violet_dates = list_violet_forecast_dates(vg_db_path)
            violet_match = suggest_forecast_date(
                selected_date=selected_date,
                available_dates=violet_dates,
            )
            if not violet_dates or str(violet_match or "") != str(selected_date):
                return {
                    "status": "GREEN",
                    "reason": "ML calculations completed, but Violet scores are not ingested for selected round.",
                    "index_code": "IDX_VIOLET_MISSING",
                    "log_id": None,
                    "missing_tickers": [],
                }
            return {
                "status": "BLUE",
                "reason": "ML data available and calculations completed.",
                "index_code": "IDX_CALC_COMPLETE",
                "log_id": None,
                "missing_tickers": [],
            }

    if latest is not None and str(latest.get("status") or "") == "success":
        return {
            "status": "GREEN",
            "reason": "ML input data available; calculations are incomplete for selected round.",
            "index_code": "IDX_CALC_INCOMPLETE",
            "log_id": None,
            "missing_tickers": [],
        }

    return {
        "status": "GREEN",
        "reason": "ML input data available; calculations not yet executed for selected round.",
        "index_code": "IDX_CALC_PENDING",
        "log_id": None,
        "missing_tickers": [],
    }
