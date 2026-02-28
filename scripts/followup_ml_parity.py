#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
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


def _resolve_snapshot_source(src: Path, dst_name: str, round_id: str) -> Path:
    """Resolve artifact source with backwards-compatible fallbacks."""
    if src.exists():
        return src

    rid = str(round_id)
    # Legacy dashboard naming used earlier in the migration.
    if dst_name == "dashboard.md":
        legacy = paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{rid}_draft.md"
        if legacy.exists():
            return legacy

    return src


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
        src_resolved = _resolve_snapshot_source(src, dst_name, round_id)
        dst = round_fixture_dir / dst_name
        if src_resolved.exists():
            shutil.copy2(src_resolved, dst)
            copied.append(dst_name)
        elif required:
            missing_required.append(str(src_resolved))
        else:
            missing_optional.append(str(src_resolved))

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


def _is_numeric_text(s: str) -> bool:
    t = str(s).strip()
    if t == "" or t.lower() in {"nan", "none", "null", "-"}:
        return False
    try:
        float(t)
        return True
    except Exception:
        return False


def _normalize_json_value(value: Any, key: str = "") -> Any:
    volatile_keys = {
        "generated_at",
        "finalized_at",
        "updated_at",
        "captured_at",
    }
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if k in volatile_keys:
                out[k] = "<IGNORED>"
            else:
                out[k] = _normalize_json_value(v, key=k)
        return out
    if isinstance(value, list):
        return [_normalize_json_value(v, key=key) for v in value]
    if isinstance(value, str):
        # Normalize path-like fields to basename for portability.
        if key.endswith("_csv") or key.endswith("_md") or key.endswith("_path"):
            return Path(value).name
        return value
    return value


def _compare_json(actual_path: Path, fixture_path: Path) -> Tuple[bool, str]:
    try:
        actual = json.loads(actual_path.read_text(encoding="utf-8"))
        expected = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"JSON read/parse error: {e}"

    a_norm = _normalize_json_value(actual)
    e_norm = _normalize_json_value(expected)
    if a_norm == e_norm:
        return True, "ok"
    return False, "normalized JSON differs"


def _compare_csv(actual_path: Path, fixture_path: Path, tol: float) -> Tuple[bool, str]:
    try:
        with actual_path.open(newline="", encoding="utf-8") as fa:
            actual_rows = list(csv.DictReader(fa))
            actual_header = list(actual_rows[0].keys()) if actual_rows else []
        with fixture_path.open(newline="", encoding="utf-8") as ff:
            expected_rows = list(csv.DictReader(ff))
            expected_header = list(expected_rows[0].keys()) if expected_rows else []
    except Exception as e:
        return False, f"CSV read error: {e}"

    # Recover headers for empty files.
    if not actual_header:
        with actual_path.open(newline="", encoding="utf-8") as fa:
            actual_header = list((csv.DictReader(fa)).fieldnames or [])
    if not expected_header:
        with fixture_path.open(newline="", encoding="utf-8") as ff:
            expected_header = list((csv.DictReader(ff)).fieldnames or [])

    if actual_header != expected_header:
        return False, f"header mismatch: actual={actual_header} expected={expected_header}"
    if len(actual_rows) != len(expected_rows):
        return False, f"row count mismatch: actual={len(actual_rows)} expected={len(expected_rows)}"

    volatile_cols = {"generated_at", "finalized_at", "updated_at", "captured_at"}
    for i, (ar, er) in enumerate(zip(actual_rows, expected_rows), start=1):
        for col in actual_header:
            if col in volatile_cols:
                continue
            av = str(ar.get(col, "")).strip()
            ev = str(er.get(col, "")).strip()
            if _is_numeric_text(av) and _is_numeric_text(ev):
                af = float(av)
                ef = float(ev)
                if not math.isfinite(af) and not math.isfinite(ef):
                    continue
                if abs(af - ef) > tol:
                    return False, f"row {i} col {col} numeric mismatch: {af} vs {ef}"
            else:
                if av != ev:
                    return False, f"row {i} col {col} mismatch: {av!r} vs {ev!r}"
    return True, "ok"


def _compare_md(actual_path: Path, fixture_path: Path) -> Tuple[bool, str]:
    try:
        a_lines = actual_path.read_text(encoding="utf-8").splitlines()
        e_lines = fixture_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return False, f"Markdown read error: {e}"

    def norm(lines: List[str]) -> List[str]:
        out: List[str] = []
        for line in lines:
            if line.startswith("- Generated at:"):
                out.append("- Generated at: <IGNORED>")
            else:
                out.append(line.rstrip())
        return out

    if norm(a_lines) == norm(e_lines):
        return True, "ok"
    return False, "markdown differs"


def _compare_file(actual_path: Path, fixture_path: Path, tol: float) -> Tuple[bool, str]:
    name = fixture_path.name.lower()
    if name.endswith(".json"):
        return _compare_json(actual_path, fixture_path)
    if name.endswith(".csv"):
        return _compare_csv(actual_path, fixture_path, tol)
    if name.endswith(".md"):
        return _compare_md(actual_path, fixture_path)

    # Generic byte compare fallback.
    try:
        if actual_path.read_bytes() == fixture_path.read_bytes():
            return True, "ok"
        return False, "binary/text differs"
    except Exception as e:
        return False, f"compare error: {e}"


def compare_round(round_id: str, fixture_root: Path, tol: float) -> int:
    fixture_root = fixture_root.resolve()
    round_fixture_dir = fixture_root / str(round_id)
    if not round_fixture_dir.exists():
        print(f"[followup-ml-parity] Fixture round not found: {round_fixture_dir}")
        return 2

    plan = _artifact_plan(round_id)
    report_rows: List[Dict[str, str]] = []
    failures = 0

    for actual_path, fixture_name, _required in plan:
        fixture_path = round_fixture_dir / fixture_name
        if not fixture_path.exists():
            report_rows.append({"file": fixture_name, "status": "SKIP", "detail": "fixture_missing"})
            continue
        if not actual_path.exists():
            report_rows.append({"file": fixture_name, "status": "FAIL", "detail": "actual_missing"})
            failures += 1
            continue

        ok, detail = _compare_file(actual_path, fixture_path, tol)
        if ok:
            report_rows.append({"file": fixture_name, "status": "PASS", "detail": detail})
        else:
            report_rows.append({"file": fixture_name, "status": "FAIL", "detail": detail})
            failures += 1

    reports_dir = paths.OUT_I_CALC_FOLLOWUP_ML_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"parity_{round_id}.md"

    lines: List[str] = []
    lines.append(f"# Follow-up ML Parity Report - {round_id}")
    lines.append("")
    lines.append(f"- Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"- Fixture root: `{fixture_root}`")
    lines.append(f"- Tolerance: `{tol}`")
    lines.append(f"- Result: `{'PASS' if failures == 0 else 'FAIL'}`")
    lines.append("")
    lines.append("| File | Status | Detail |")
    lines.append("|:--|:--|:--|")
    for row in report_rows:
        lines.append(f"| {row['file']} | {row['status']} | {row['detail']} |")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("[followup-ml-parity] Compare complete:")
    print(f"  round_id={round_id}")
    print(f"  failures={failures}")
    print(f"  report={report_path}")
    for row in report_rows:
        print(f"  - {row['status']} {row['file']}: {row['detail']}")

    return 0 if failures == 0 else 1


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

    pc = sub.add_parser("compare", help="Compare round artifacts against parity fixtures")
    pc.add_argument("--round-id", required=True, help="Round identifier, e.g. 26-1-09")
    pc.add_argument(
        "--fixture-root",
        default=str(_default_fixture_root()),
        help="Fixture root directory (default: tests/fixtures/followup_ml/parity)",
    )
    pc.add_argument(
        "--tol",
        type=float,
        default=1e-6,
        help="Numeric tolerance for CSV comparisons (default: 1e-6)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "snapshot":
        return snapshot_round(str(args.round_id), Path(str(args.fixture_root)))
    if args.cmd == "compare":
        return compare_round(str(args.round_id), Path(str(args.fixture_root)), float(args.tol))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
