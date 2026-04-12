from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.ui.services.ann_ingredients_pipeline import (  # noqa: E402
    normalize_ticker_list,
    resolve_processing_dates,
    run_ann_ingredients_for_dates,
    write_run_summary,
)
from src.ui.services.pipeline_runner import TICKER_ORDER  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Fully automated ANN ingredient pipeline: TI/PP backfill + SVL + TDA + FH3 + ANN ingest."
        )
    )
    p.add_argument(
        "--start-date",
        type=str,
        default="2025-07-29",
        help="Inclusive start date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--end-date",
        type=str,
        default="",
        help="Inclusive end date (YYYY-MM-DD). Empty means latest available date.",
    )
    p.add_argument(
        "--dates",
        nargs="*",
        default=None,
        help="Optional explicit date list. If provided, sidebar date source is not used.",
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        default=list(TICKER_ORDER),
        help="Logical tickers. Default: TNX DJI SPX VIX QQQ AAPL.",
    )
    p.add_argument(
        "--python-exec",
        type=str,
        default=sys.executable,
        help="Python executable for subprocess stages.",
    )
    p.add_argument(
        "--ingest-mode",
        choices=["per-date", "end"],
        default="per-date",
        help="Run ANN feature ingest after each date (per-date) or once at end (end).",
    )
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue next date after a failure. Default is fail-fast.",
    )
    p.add_argument(
        "--log-dir",
        type=str,
        default="",
        help="Optional summary log directory override.",
    )
    return p


def _print_progress(event: dict[str, Any]) -> None:
    event_name = str(event.get("event") or "")
    if event_name == "stage_start":
        print(
            "[ann_ingredients] "
            f"date={event.get('selected_date')} "
            f"stage={event.get('stage')} status=running"
        )
        return
    if event_name == "stage_done":
        print(
            "[ann_ingredients] "
            f"date={event.get('selected_date')} "
            f"stage={event.get('stage')} rc={event.get('returncode')} "
            f"sec={float(event.get('duration_seconds') or 0.0):.2f}"
        )
        stdout = str(event.get("stdout") or "").strip()
        if stdout:
            for line in stdout.splitlines():
                print(f"[ann_ingredients][stdout] {line}")
        stderr = str(event.get("stderr") or "").strip()
        if stderr:
            for line in stderr.splitlines():
                print(f"[ann_ingredients][stderr] {line}")
        return
    if event_name == "date_done":
        print(
            "[ann_ingredients] "
            f"date={event.get('selected_date')} "
            f"status={event.get('status')}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    tickers = normalize_ticker_list([str(x) for x in list(args.tickers or [])])
    dates = resolve_processing_dates(
        start_date=str(args.start_date),
        end_date=str(args.end_date or "").strip() or None,
        explicit_dates=list(args.dates) if args.dates else None,
    )
    if not dates:
        print("[ann_ingredients] No dates selected after filters.")
        return 0

    print(
        "[ann_ingredients] "
        f"dates={len(dates)} range={dates[0]}..{dates[-1]} "
        f"tickers={' '.join(tickers)} ingest_mode={args.ingest_mode}"
    )

    summary = run_ann_ingredients_for_dates(
        dates=dates,
        tickers=tickers,
        python_exec=str(args.python_exec),
        ingest_after_each_date=str(args.ingest_mode) == "per-date",
        stop_on_error=not bool(args.continue_on_error),
        progress_callback=_print_progress,
    )

    log_path = write_run_summary(
        summary=summary,
        log_dir=Path(args.log_dir).resolve() if str(args.log_dir).strip() else None,
    )
    print(
        "[ann_ingredients] "
        f"completed status={summary.get('status')} "
        f"success={summary.get('success_count')} failed={summary.get('failed_count')}"
    )
    if summary.get("failed_stage"):
        print(
            "[ann_ingredients] "
            f"first_failure date={summary.get('failed_date')} stage={summary.get('failed_stage')}"
        )
    print(f"[ann_ingredients] summary_log={log_path}")
    return 0 if str(summary.get("status") or "") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
