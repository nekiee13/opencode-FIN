from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _bootstrap_sys_path() -> Path:
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


APP_ROOT = _bootstrap_sys_path()

from src.config import paths  # noqa: E402
from src.ui.services.batch_chain import load_dates_for_batch, run_full_chain_for_dates  # noqa: E402


def _format_hms(seconds: float) -> str:
    total = max(int(round(float(seconds))), 0)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return int(float(text))
            except ValueError:
                return default
    return default


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return float(text)
            except ValueError:
                return default
    return default


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run Streamlit-equivalent backend chain for a date range: "
            "ML pipeline -> anchored backfill -> materialize (Load Blue/Green) -> QA log."
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
        "--ticker",
        type=str,
        default="ALL",
        help="Ticker scope for ML pipeline commands. Default ALL.",
    )
    p.add_argument(
        "--python-exec",
        type=str,
        default="",
        help="Optional python executable override used for spawned scripts.",
    )
    p.add_argument(
        "--skip-load-blue-green",
        action="store_true",
        help="Skip explicit load/materialize step after anchored backfill.",
    )
    p.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop batch immediately when one date fails.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    start_date = str(args.start_date or "").strip()
    end_date = str(args.end_date or "").strip() or None
    ticker = str(args.ticker or "ALL").strip() or "ALL"
    python_exec = str(args.python_exec or "").strip() or None
    run_load = not bool(args.skip_load_blue_green)
    stop_on_error = bool(args.stop_on_error)

    dates = load_dates_for_batch(start_date=start_date, end_date=end_date)
    if not dates:
        print("[streamlit-full-chain] No dates selected after filter.")
        return 0

    print(
        f"[streamlit-full-chain] Running {len(dates)} date(s) "
        f"from {dates[0]} to {dates[-1]} with ticker={ticker}."
    )

    batch_dir = (paths.OUT_I_CALC_DIR / "gui_ops" / "batch").resolve()
    batch_dir.mkdir(parents=True, exist_ok=True)
    status_path = batch_dir / "streamlit_full_chain_current_status.json"

    def _progress_logger(event: dict[str, object]) -> None:
        event_name = str(event.get("event") or "")
        if event_name != "date_complete":
            return
        idx = _as_int(event.get("index"), 0)
        total = _as_int(event.get("total"), 0)
        selected = str(event.get("selected_date") or "")
        overall_status = str(event.get("overall_status") or "unknown")
        success_count = _as_int(event.get("success_count"), 0)
        failed_count = _as_int(event.get("failed_count"), 0)
        elapsed_seconds = _as_float(event.get("elapsed_seconds"), 0.0)
        eta_seconds = _as_float(event.get("eta_seconds"), 0.0)
        print(
            "[streamlit-full-chain] "
            f"[{idx}/{total}] {selected} | status={overall_status} "
            f"success={success_count} failed={failed_count} "
            f"elapsed={_format_hms(elapsed_seconds)} eta={_format_hms(eta_seconds)}"
        )

        status_payload = {
            "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "index": idx,
            "total": total,
            "selected_date": selected,
            "overall_status": overall_status,
            "success_count": success_count,
            "failed_count": failed_count,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "eta_seconds": round(eta_seconds, 3),
        }
        status_path.write_text(json.dumps(status_payload, indent=2), encoding="utf-8")

    summary = run_full_chain_for_dates(
        dates=dates,
        selected_ticker=ticker,
        python_exec=python_exec,
        run_load_blue_green=run_load,
        stop_on_error=stop_on_error,
        progress_callback=_progress_logger,
    )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = batch_dir / f"streamlit_full_chain_{dates[0]}_{dates[-1]}_{stamp}.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        "[streamlit-full-chain] Completed: "
        f"success={summary['success_count']} failed={summary['failed_count']}"
    )
    print(f"[streamlit-full-chain] Summary log: {out_path}")

    failed_count = int(summary.get("failed_count") or 0)
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
