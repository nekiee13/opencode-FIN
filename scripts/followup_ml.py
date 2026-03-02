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


def _import_followup_module():
    try:
        import src.followup_ml as followup_ml  # type: ignore

        return followup_ml
    except ModuleNotFoundError as e:
        print("[followup-ml] Missing Python dependency.")
        print(f"  {e}")
        print("[followup-ml] Activate project venv and install requirements, then retry.")
        print("  Example: python -m pip install -r requirements.txt")
        return None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_ml.py",
        description="Follow-up ML pipeline tools (draft, finalize, dashboard).",
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

    p_finalize = sub.add_parser(
        "finalize",
        help="Ingest +3 actuals and update round state (draft/partial/final/revised)",
    )
    p_finalize.add_argument("--round-id", required=True, help="Round identifier")
    p_finalize.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional logical tickers override",
    )
    p_finalize.add_argument(
        "--actual-lookup-date",
        type=str,
        default=None,
        help="Optional fixed lookup date override for all tickers (yyyy-mm-dd).",
    )
    p_finalize.add_argument(
        "--allow-lookup-override",
        action="store_true",
        help="Require explicit opt-in when using --actual-lookup-date.",
    )
    p_finalize.add_argument(
        "--override-reason",
        type=str,
        default=None,
        help="Break-glass reason for override mode.",
    )
    p_finalize.add_argument(
        "--override-ticket",
        type=str,
        default=None,
        help="Change/ticket reference for override mode.",
    )
    p_finalize.add_argument(
        "--override-approver",
        type=str,
        default=None,
        help="Approver identity for override mode.",
    )

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "draft":
        mod = _import_followup_module()
        if mod is None:
            return 3

        artifacts = mod.run_t0_draft_round(
            round_id=str(args.round_id),
            tickers=args.tickers,
            fh=args.fh,
        )
        print("[followup-ml] Draft round artifacts written:")
        print(f"  {artifacts.context_json}")
        print(f"  {artifacts.forecasts_csv}")
        print(f"  {artifacts.draft_metrics_csv}")
        print(f"  {artifacts.day3_matrix_csv}")
        print(f"  {artifacts.weighted_ensemble_csv}")
        print(f"  {artifacts.dashboard_md}")
        try:
            print(f"  dashboard_size_bytes={artifacts.dashboard_md.stat().st_size}")
        except OSError:
            pass
        return 0

    if args.cmd == "board":
        mod = _import_followup_module()
        if mod is None:
            return 3

        out = mod.render_t0_dashboard_for_round(str(args.round_id))
        print("[followup-ml] Dashboard rendered:")
        print(f"  {out}")
        try:
            print(f"  dashboard_size_bytes={out.stat().st_size}")
        except OSError:
            pass
        return 0

    if args.cmd == "finalize":
        mod = _import_followup_module()
        if mod is None:
            return 3

        artifacts = mod.run_tplus3_finalize_round(
            round_id=str(args.round_id),
            tickers=args.tickers,
            actual_lookup_date=args.actual_lookup_date,
            allow_lookup_override=bool(args.allow_lookup_override),
            override_reason=args.override_reason,
            override_ticket=args.override_ticket,
            override_approver=args.override_approver,
        )
        print("[followup-ml] Round finalized:")
        print(f"  lookup_date_override={args.actual_lookup_date or '-'}")
        print(f"  run_mode={artifacts.run_mode}")
        print(f"  state={artifacts.round_state}")
        print(f"  actuals_ok={artifacts.ok_actuals}/{artifacts.total_actuals}")
        print(
            f"  scores_computed={artifacts.scored_rows}/{artifacts.total_score_rows}"
        )
        print(
            f"  transforms_mapped={artifacts.mapped_rows}/{artifacts.total_score_rows}"
        )
        print(
            "  model_coverage_avg="
            f"{artifacts.model_coverage_avg:.3f}"
        )
        print(f"  {artifacts.actuals_csv}")
        print(f"  {artifacts.partial_scores_csv}")
        print(f"  {artifacts.model_summary_csv}")
        print(f"  {artifacts.avr_history_csv}")
        print(f"  {artifacts.avr_summary_csv}")
        print(f"  {artifacts.next_weights_csv}")
        print(f"  {artifacts.context_json}")
        print(f"  {artifacts.dashboard_md}")
        try:
            print(f"  dashboard_size_bytes={artifacts.dashboard_md.stat().st_size}")
        except OSError:
            pass
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
