from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.pipeline_runner import TICKER_ORDER
from src.ui.services.run_registry import latest_run_for_date
from src.ui.services.vg_loader import list_violet_forecast_dates, suggest_forecast_date

_CORE_STAGES: tuple[str, ...] = ("svl_export", "tda_export", "make_fh3_table")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _core_success_for_all_tickers(run_payload: dict[str, Any]) -> bool:
    stages = list(run_payload.get("stages", []))
    success_set = {
        (str(item.get("ticker") or ""), str(item.get("stage") or ""))
        for item in stages
        if str(item.get("status") or "") == "success"
    }
    for ticker in TICKER_ORDER:
        for stage_name in _CORE_STAGES:
            if (ticker, stage_name) not in success_set:
                return False
    return True


def evaluate_pipeline_state(
    *,
    selected_date: str,
    runs_root: Path | None = None,
    vg_db_path: Path | None = None,
) -> dict[str, Any]:
    latest = latest_run_for_date(selected_date, root_dir=runs_root)
    violet_dates = list_violet_forecast_dates(vg_db_path)
    suggested_violet = suggest_forecast_date(
        selected_date=selected_date,
        available_dates=violet_dates,
    )

    report: dict[str, Any] = {
        "selected_date": str(selected_date),
        "generated_at": _now_iso(),
        "latest_run_id": str(latest.get("run_id")) if latest else None,
        "latest_run_status": str(latest.get("status")) if latest else None,
        "latest_run_created_at": str(latest.get("created_at")) if latest else None,
        "core_success_all_tickers": bool(_core_success_for_all_tickers(latest))
        if latest
        else False,
        "has_violet_rows": bool(violet_dates),
        "violet_dates_count": int(len(violet_dates)),
        "violet_for_selected_date": str(selected_date) in set(violet_dates),
        "suggested_violet_date": suggested_violet,
        "index_code": "QA_UNKNOWN",
        "summary": "",
    }

    if latest is None:
        report["index_code"] = "QA_RUN_MISSING"
        report["summary"] = "No pipeline run record found for selected date."
        return report

    if str(latest.get("status") or "") == "failed":
        report["index_code"] = "QA_RUN_FAILED"
        report["summary"] = (
            "Latest pipeline run failed. Inspect stage logs in run registry."
        )
        return report

    if not bool(report["core_success_all_tickers"]):
        report["index_code"] = "QA_CORE_INCOMPLETE"
        report["summary"] = "Core ticker stages are incomplete for selected date."
        return report

    if not bool(report["has_violet_rows"]):
        report["index_code"] = "QA_VIOLET_MISSING"
        report["summary"] = "No Violet scores are ingested in ML_VG store."
        return report

    if not bool(report["violet_for_selected_date"]):
        report["index_code"] = "QA_VIOLET_DATE_MISMATCH"
        report["summary"] = "Violet scores exist, but selected date is missing."
        return report

    report["index_code"] = "QA_OK"
    report["summary"] = (
        "Pipeline run and Violet ingestion are aligned for selected date."
    )
    return report


def write_pipeline_qa_log(
    *,
    report: dict[str, Any],
    root_dir: Path | None = None,
) -> Path:
    base = (root_dir or (paths.OUT_I_CALC_DIR / "gui_ops" / "qa")).resolve()
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    selected = str(report.get("selected_date") or "unknown").replace("/", "-")
    index_code = str(report.get("index_code") or "QA_UNKNOWN")
    out_path = base / f"{stamp}_{selected}_{index_code}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path
