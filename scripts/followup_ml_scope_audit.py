#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
        prog="followup_ml_scope_audit.py",
        description="Run weekly M5 scope-label audit for merged PRs.",
    )
    p.add_argument(
        "--since",
        required=True,
        help="Audit window start (YYYY-MM-DD).",
    )
    p.add_argument(
        "--repo",
        default=None,
        help="GitHub repository in OWNER/REPO format (default: infer from origin).",
    )
    p.add_argument(
        "--report-path",
        default=None,
        help="Optional explicit markdown report path.",
    )
    p.add_argument(
        "--write-report",
        action="store_true",
        help="Write markdown report to default report path.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary.",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        from src.followup_ml.scope_audit import (
            ScopeAuditError,
            run_scope_audit,
            write_scope_audit_report,
        )
    except ModuleNotFoundError as e:
        print("[followup-ml-scope-audit] Missing Python dependency.")
        print(f"  {e}")
        print(
            "[followup-ml-scope-audit] Activate project venv and install requirements, then retry."
        )
        print("  Example: python -m pip install -r requirements.txt")
        return 3

    try:
        result = run_scope_audit(repo=args.repo, since=str(args.since))
    except ScopeAuditError as e:
        print(f"[followup-ml-scope-audit] ERROR: {e}")
        return 2

    status = "PASS" if result.violations_count == 0 else "FAIL"
    print("[followup-ml-scope-audit] Complete:")
    print(f"  repo={result.repo}")
    print(f"  since={result.since}")
    print(f"  total_merged_prs={result.total_merged_prs}")
    print(f"  exception_merges={result.exception_merges_count}")
    print(f"  missing_scope_label_merges={result.missing_scope_label_merges_count}")
    print(f"  violations={result.violations_count}")
    print(f"  result={status}")

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))

    report_path: Optional[Path] = None
    if args.report_path:
        report_path = Path(str(args.report_path))
    if args.write_report or report_path is not None:
        written = write_scope_audit_report(result, out_path=report_path)
        print(f"  report={written}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
