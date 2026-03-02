#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Set


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


def _load_parity_module():
    script_path = APP_ROOT / "scripts" / "followup_ml_parity.py"
    spec = importlib.util.spec_from_file_location("followup_ml_parity", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load parity module from {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_round_outputs(mod, round_id: str, fixture_root: Path) -> None:
    fixture_round_dir = fixture_root / str(round_id)
    if not fixture_round_dir.exists():
        raise FileNotFoundError(f"Fixture round not found: {fixture_round_dir}")

    for actual_path, fixture_name, required in mod._artifact_plan(str(round_id)):
        fixture_path = fixture_round_dir / fixture_name
        if fixture_path.exists():
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture_path, actual_path)
        elif required:
            raise FileNotFoundError(f"Required fixture missing: {fixture_path}")


def _collect_skips(report_path: Path) -> Set[str]:
    skips: Set[str] = set()
    if not report_path.exists():
        return skips
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        parts = [p.strip() for p in line.strip().split("|")]
        if len(parts) < 4:
            continue
        file_name = parts[1]
        status = parts[2]
        detail = parts[3]
        if status == "SKIP" and detail == "fixture_missing":
            skips.add(file_name)
    return skips


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_ml_ci_parity_gate.py",
        description="Fixture-driven parity gate for CI benchmark rounds.",
    )
    p.add_argument(
        "--round-id",
        action="append",
        dest="round_ids",
        help="Round identifier. Repeat for multiple rounds.",
    )
    p.add_argument(
        "--fixture-root",
        type=str,
        default=str(APP_ROOT / "tests" / "fixtures" / "followup_ml" / "parity"),
        help="Fixture root directory.",
    )
    p.add_argument(
        "--tol",
        type=float,
        default=1e-6,
        help="Numeric tolerance for CSV comparisons.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    round_ids = args.round_ids or ["26-1-06", "26-1-09", "26-1-11"]
    fixture_root = Path(str(args.fixture_root)).resolve()
    tol = float(args.tol)

    allowed_skips_by_round: Dict[str, Set[str]] = {
        "26-1-09": {"t0_day3_weighted_ensemble.csv"},
    }

    mod = _load_parity_module()
    failures: List[str] = []

    for round_id in round_ids:
        try:
            _seed_round_outputs(mod, str(round_id), fixture_root)
        except Exception as e:
            failures.append(f"{round_id}: seed_failed: {e}")
            continue

        rc = int(mod.compare_round(str(round_id), fixture_root, tol))
        report_path = mod.paths.OUT_I_CALC_FOLLOWUP_ML_DIR / "reports" / f"parity_{round_id}.md"
        skips = _collect_skips(report_path)
        allowed = allowed_skips_by_round.get(str(round_id), set())
        unexpected = sorted(skips.difference(allowed))
        if unexpected:
            failures.append(
                f"{round_id}: unexpected_skips={','.join(unexpected)} allowed={','.join(sorted(allowed))}"
            )
        if rc != 0:
            failures.append(f"{round_id}: compare_failed")

    if failures:
        print("[followup-ml-ci-parity] FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("[followup-ml-ci-parity] PASS")
    for rid in round_ids:
        print(f"  - {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
