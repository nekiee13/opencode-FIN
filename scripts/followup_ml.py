#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent

    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    compat_dir = app_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))

    return app_root


APP_ROOT = _bootstrap_sys_path()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_ml.py",
        description="Follow-up ML pipeline tools (T0 draft and dashboard rendering).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_draft = sub.add_parser("draft", help="Create T0 draft round artifacts and dashboard")
    p_draft.add_argument("--round-id", required=True, help="Round identifier, e.g. 26-1-06")
    p_draft.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional logical tickers (default: TNX DJI SPX VIX QQQ AAPL)",
    )
    p_draft.add_argument("--fh", type=int, default=None, help="Forecast horizon override")

    p_board = sub.add_parser("board", help="Re-render dashboard from persisted round data")
    p_board.add_argument("--round-id", required=True, help="Round identifier")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "draft":
        from src.followup_ml import run_t0_draft_round

        artifacts = run_t0_draft_round(
            round_id=str(args.round_id),
            tickers=args.tickers,
            fh=args.fh,
        )
        print("[followup-ml] Draft round artifacts written:")
        print(f"  {artifacts.context_json}")
        print(f"  {artifacts.forecasts_csv}")
        print(f"  {artifacts.draft_metrics_csv}")
        print(f"  {artifacts.day3_matrix_csv}")
        print(f"  {artifacts.dashboard_md}")
        return 0

    if args.cmd == "board":
        from src.followup_ml import render_t0_dashboard_for_round

        out = render_t0_dashboard_for_round(str(args.round_id))
        print("[followup-ml] Dashboard rendered:")
        print(f"  {out}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
