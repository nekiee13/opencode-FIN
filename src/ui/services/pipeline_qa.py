from __future__ import annotations

import json
import csv
import sqlite3
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


def _list_partial_score_forecast_dates(scores_dir: Path) -> list[str]:
    if not scores_dir.exists():
        return []

    dates: set[str] = set()
    for csv_path in sorted(scores_dir.glob("*_partial_scores.csv")):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    raw = str(row.get("forecast_date") or "").strip()
                    if raw and raw.lower() != "nan":
                        dates.add(raw)
        except OSError:
            continue

    return sorted(dates)


def _materialized_counts_for_date(
    vg_db_path: Path | None, selected_date: str
) -> dict[str, int]:
    use_path = (vg_db_path or paths.OUT_I_CALC_ML_VG_DB_PATH).resolve()
    if not use_path.exists():
        return {}

    conn = sqlite3.connect(str(use_path))
    try:
        rows = conn.execute(
            """
            SELECT table_name, COUNT(*) AS c
            FROM materialized_scores
            WHERE forecast_date = ?
            GROUP BY table_name
            """,
            (str(selected_date),),
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()

    return {str(r[0]): int(r[1]) for r in rows}


def evaluate_pipeline_state(
    *,
    selected_date: str,
    runs_root: Path | None = None,
    vg_db_path: Path | None = None,
    scores_dir: Path | None = None,
) -> dict[str, Any]:
    latest = latest_run_for_date(selected_date, root_dir=runs_root)
    violet_dates = list_violet_forecast_dates(vg_db_path)
    use_scores_dir = (scores_dir or paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR).resolve()
    partial_score_dates = _list_partial_score_forecast_dates(use_scores_dir)
    suggested_violet = suggest_forecast_date(
        selected_date=selected_date,
        available_dates=violet_dates,
    )
    materialized_counts = _materialized_counts_for_date(vg_db_path, selected_date)

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
        "partial_scores_dir": str(use_scores_dir),
        "partial_scores_dates_count": int(len(partial_score_dates)),
        "partial_scores_has_selected_date": str(selected_date)
        in set(partial_score_dates),
        "partial_scores_sample_dates": partial_score_dates[-10:],
        "materialized_counts": materialized_counts,
        "materialized_has_selected_date": bool(materialized_counts),
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
        if bool(report["partial_scores_has_selected_date"]):
            report["index_code"] = "QA_VG_INGEST_MISSING"
            report["summary"] = (
                "Partial scores exist for selected date, but ML_VG Violet ingestion was not executed. "
                "Run followup_ml_vg ingest-round for the related round_id."
            )
        else:
            report["index_code"] = "QA_PARTIAL_SCORES_MISSING"
            report["summary"] = (
                "No partial score artifacts found for selected date. "
                "Run followup_ml finalize flow first, then ingest into ML_VG."
            )
        return report

    if not bool(report["violet_for_selected_date"]):
        report["index_code"] = "QA_VIOLET_DATE_MISMATCH"
        report["summary"] = "Violet scores exist, but selected date is missing."
        return report

    if not bool(report["materialized_has_selected_date"]):
        report["index_code"] = "QA_MATERIALIZE_MISSING"
        report["summary"] = (
            "Violet rows exist, but no materialized blue/green/violet snapshot exists for selected date. "
            "Run Blue/Green materialization."
        )
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
