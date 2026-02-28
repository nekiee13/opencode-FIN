#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


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

from src.config import paths


MANIFEST_SCHEMA = "followup-ml-parity-v1"


def _default_fixture_root() -> Path:
    return APP_ROOT / "tests" / "fixtures" / "followup_ml" / "parity"


def _artifact_plan(round_id: str) -> List[Tuple[Path, str, bool]]:
    rid = str(round_id)
    return [
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "round_context.json", "round_context.json", True),
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "t0_forecasts.csv", "t0_forecasts.csv", True),
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "t0_draft_metrics.csv", "t0_draft_metrics.csv", True),
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "t0_day3_matrix.csv", "t0_day3_matrix.csv", True),
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "t0_day3_weighted_ensemble.csv", "t0_day3_weighted_ensemble.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / rid / "actuals_tplus3.csv", "actuals_tplus3.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR / f"{rid}_partial_scores.csv", "partial_scores.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR / f"{rid}_model_summary.csv", "model_summary.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_AVR_DIR / f"{rid}_avr_summary.csv", "avr_summary.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR / f"{rid}_next_weights.csv", "next_weights.csv", False),
        (paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{rid}.md", "dashboard.md", False),
    ]


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "schema": MANIFEST_SCHEMA,
            "updated_at": "",
            "rounds": {},
        }
    try:
        return cast_manifest(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {
            "schema": MANIFEST_SCHEMA,
            "updated_at": "",
            "rounds": {},
        }


def cast_manifest(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    return {}


def _write_manifest(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def snapshot_round(round_id: str, fixture_root: Path) -> int:
    fixture_root = fixture_root.resolve()
    round_fixture_dir = fixture_root / str(round_id)
    round_fixture_dir.mkdir(parents=True, exist_ok=True)

    plan = _artifact_plan(round_id)
    copied: List[str] = []
    missing_required: List[str] = []
    missing_optional: List[str] = []

    for src, dst_name, required in plan:
        dst = round_fixture_dir / dst_name
        if src.exists():
            shutil.copy2(src, dst)
            copied.append(dst_name)
        elif required:
            missing_required.append(str(src))
        else:
            missing_optional.append(str(src))

    if missing_required:
        print("[followup-ml-parity] Missing required artifacts:")
        for p in missing_required:
            print(f"  {p}")
        return 2

    round_state = ""
    context_path = round_fixture_dir / "round_context.json"
    if context_path.exists():
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
            round_state = str(context.get("round_state", ""))
        except Exception:
            round_state = ""

    manifest_path = fixture_root / "manifest.json"
    manifest = _load_manifest(manifest_path)
    rounds = cast_manifest(manifest.get("rounds"))
    rounds[str(round_id)] = {
        "state": round_state,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fixture_dir": str(round_fixture_dir.relative_to(fixture_root)),
        "files": copied,
        "missing_optional": [Path(p).name for p in missing_optional],
    }
    manifest["schema"] = MANIFEST_SCHEMA
    manifest["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    manifest["rounds"] = rounds
    _write_manifest(manifest_path, manifest)

    print("[followup-ml-parity] Snapshot complete:")
    print(f"  round_id={round_id}")
    print(f"  fixture_dir={round_fixture_dir}")
    print(f"  copied_files={len(copied)}")
    for name in copied:
        print(f"  - {name}")
    if missing_optional:
        print(f"  missing_optional={len(missing_optional)}")
    print(f"  manifest={manifest_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_ml_parity.py",
        description="Create follow-up ML parity fixtures from generated artifacts.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("snapshot", help="Snapshot one round into test fixtures")
    ps.add_argument("--round-id", required=True, help="Round identifier, e.g. 26-1-09")
    ps.add_argument(
        "--fixture-root",
        default=str(_default_fixture_root()),
        help="Fixture root directory (default: tests/fixtures/followup_ml/parity)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "snapshot":
        return snapshot_round(str(args.round_id), Path(str(args.fixture_root)))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
