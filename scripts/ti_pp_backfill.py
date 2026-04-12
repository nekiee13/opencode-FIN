from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.ui.services.pipeline_runner import TICKER_ORDER  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Replay-date anchored TI/PP backfill for ANN ingredient coverage. "
            "Generates TI and PP snapshots without GUI/manual steps."
        )
    )
    p.add_argument(
        "--selected-date",
        required=True,
        help="Replay anchor date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        default=list(TICKER_ORDER),
        help="Logical tickers to process. Default: TNX DJI SPX VIX QQQ AAPL.",
    )
    p.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Fail fast on first ticker error.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON payload at end of run.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    try:
        from src.ui.services.ti_pp_backfill import backfill_ti_pp_for_date
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "dependency")
        print(f"[ti_pp_backfill] Missing Python dependency: {missing}")
        print("[ti_pp_backfill] Activate project environment and install requirements.")
        return 3

    out = backfill_ti_pp_for_date(
        selected_date=str(args.selected_date),
        tickers=[str(x) for x in list(args.tickers or [])],
        stop_on_error=bool(args.stop_on_error),
    )

    print(
        "[ti_pp_backfill] "
        f"selected_date={out.get('selected_date')} "
        f"status={out.get('status')} "
        f"success={out.get('success_count')} "
        f"failed={out.get('failed_count')}"
    )

    for row in list(out.get("results") or []):
        print(
            "[ti_pp_backfill] "
            f"ticker={row.get('ticker')} runtime={row.get('runtime_ticker')} "
            f"status={row.get('status')} "
            f"as_of={row.get('as_of_date') or '-'} "
            f"ti={row.get('ti_path') or '-'} pp={row.get('pp_path') or '-'} "
            f"error={row.get('error') or '-'}"
        )

    if bool(args.json):
        print(json.dumps(out, indent=2))

    return 0 if str(out.get("status") or "") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
