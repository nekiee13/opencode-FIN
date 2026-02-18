# ------------------------
# tools/golden_baseline.py
# ------------------------
"""
FIN — Golden Baseline Utility (regression harness)

Fixes in this revision (Pylance)
--------------------------------
- Avoids pandas typing ambiguity where pd.to_numeric may be inferred as scalar/float.
- Ensures numeric diff operations remain Series-typed (Series.sub + Series.abs),
  preventing "float has no attribute isna/abs" diagnostics.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Bootstrap: resolve FIN root and sys.path
# ----------------------------------------------------------------------


def _bootstrap_fin_root() -> Path:
    """
    Ensure FIN root is importable from any CWD.
    Heuristic: walk upward from this file location until a likely repo root is found.
    """
    here = Path(__file__).resolve()
    cur = here.parent
    for p in (cur, *cur.parents):
        if (p / "src").exists() and (p / "src" / "config").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            return p
        if (p / "src").exists() and (p / "config").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            return p

    fin_root = here.parents[1]
    if str(fin_root) not in sys.path:
        sys.path.insert(0, str(fin_root))
    return fin_root


FIN_ROOT = _bootstrap_fin_root()

from src.config import paths as fin_paths  # noqa: E402


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

DEFAULT_TICKERS: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")

DEFAULT_GOLDEN_DIR = (FIN_ROOT / "tools" / "_golden").resolve()
DEFAULT_RUNS_DIR = (FIN_ROOT / "tools" / "_runs" / "golden").resolve()


# ----------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    fh3_txt: Path
    fh3_csv_full: Path
    fh3_csv_min: Path
    svl_md: Path
    tda_md: Path
    meta_json: Path


@dataclass(frozen=True)
class CompareResult:
    ok: bool
    issues: List[str]


# ----------------------------------------------------------------------
# Helpers: CLI parsing
# ----------------------------------------------------------------------


def _parse_map_items(items: Sequence[str]) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for it in items:
        it = it.strip()
        if not it:
            continue
        if "=" not in it:
            raise ValueError(f"Invalid mapping '{it}'. Use KEY=VALUE (e.g., SPX=GSPC).")
        k, v = it.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            raise ValueError(f"Invalid mapping '{it}'. Use KEY=VALUE (e.g., SPX=GSPC).")
        m[k] = v
    return m


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ----------------------------------------------------------------------
# Helpers: subprocess runner
# ----------------------------------------------------------------------


def _run_cmd(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: int = 600,
) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _python_exe() -> str:
    return sys.executable or "python"


# ----------------------------------------------------------------------
# Artifact generation
# ----------------------------------------------------------------------


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _extract_fh3_tables_from_stdout(stdout: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    marker = "PASTE-READY (minimal) FORECAST_TABLE_ALL_TICKERS:"
    if marker not in stdout:
        raise ValueError("FH3 stdout did not contain expected marker for minimal table.")

    before, after = stdout.split(marker, 1)

    before_lines = [ln.rstrip("\n") for ln in before.splitlines()]
    blocks: List[List[str]] = []
    cur: List[str] = []
    for ln in before_lines:
        if ln.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    if not blocks:
        raise ValueError("FH3 stdout did not contain a parsable full table block.")
    full_text = "\n".join(blocks[-1])

    after_lines = [ln.rstrip("\n") for ln in after.splitlines()]
    blocks2: List[List[str]] = []
    cur2: List[str] = []
    for ln in after_lines:
        if ln.strip() == "":
            if cur2:
                blocks2.append(cur2)
                cur2 = []
        else:
            cur2.append(ln)
    if cur2:
        blocks2.append(cur2)
    if not blocks2:
        raise ValueError("FH3 stdout did not contain a parsable minimal table block.")
    minimal_text = "\n".join(blocks2[0])

    full_df = pd.read_fwf(StringIO(full_text))
    minimal_df = pd.read_fwf(StringIO(minimal_text))

    full_df.columns = [str(c).strip() for c in full_df.columns]
    minimal_df.columns = [str(c).strip() for c in minimal_df.columns]

    return full_df, minimal_df


def generate_artifacts(
    *,
    tickers: Sequence[str],
    prefix_map: Dict[str, str],
    run_dir: Path,
    write_metrics: bool,
    write_prompt_headers: bool,
) -> RunPaths:
    _ensure_dir(run_dir)

    fh3_txt = run_dir / "FH3_STDOUT.txt"
    fh3_csv_full = run_dir / "FH3_FULL.csv"
    fh3_csv_min = run_dir / "FH3_MINIMAL.csv"

    make_fh3 = (FIN_ROOT / "scripts" / "make_fh3_table.py").resolve()
    if not make_fh3.exists():
        raise FileNotFoundError(f"Missing script: {make_fh3}")

    rc, out, err = _run_cmd([_python_exe(), str(make_fh3)], cwd=FIN_ROOT)
    _write_text(fh3_txt, out + ("\n\n--- STDERR ---\n" + err if err else ""))
    if rc != 0:
        raise RuntimeError(f"make_fh3_table.py failed (rc={rc}). See {fh3_txt}")

    full_df, min_df = _extract_fh3_tables_from_stdout(out)
    full_df.to_csv(fh3_csv_full, index=False, encoding="utf-8")
    min_df.to_csv(fh3_csv_min, index=False, encoding="utf-8")

    svl_md = run_dir / "SVL_CONTEXT.md"
    svl_export = (FIN_ROOT / "scripts" / "svl_export.py").resolve()
    if not svl_export.exists():
        raise FileNotFoundError(f"Missing script: {svl_export}")

    svl_out_dir = run_dir / "svl"
    _ensure_dir(svl_out_dir)

    svl_cmd = [
        _python_exe(),
        str(svl_export),
        "--tickers",
        *list(tickers),
        "--csv-dir",
        str(fin_paths.DATA_RAW_DIR),
        "--csv-suffix",
        "_data.csv",
        "--out-dir",
        str(svl_out_dir),
        "--basename",
        "SVL",
        "--print",
    ]
    if prefix_map:
        svl_cmd += ["--map-json", json.dumps(prefix_map)]
    if write_metrics:
        svl_cmd += ["--write-metrics"]
    if write_prompt_headers:
        svl_cmd += ["--write-prompt-header"]

    rc, out, err = _run_cmd(svl_cmd, cwd=FIN_ROOT)
    if rc != 0:
        _write_text(run_dir / "SVL_STDOUT.txt", out)
        _write_text(run_dir / "SVL_STDERR.txt", err)
        raise RuntimeError(f"svl_export.py failed (rc={rc}). See SVL_STDERR.txt in {run_dir}")
    _write_text(svl_md, out)

    tda_md = run_dir / "TDA_CONTEXT.md"
    tda_export = (FIN_ROOT / "scripts" / "tda_export.py").resolve()
    if not tda_export.exists():
        raise FileNotFoundError(f"Missing script: {tda_export}")

    tda_out_dir = run_dir / "tda"
    _ensure_dir(tda_out_dir)

    tda_cmd = [
        _python_exe(),
        str(tda_export),
        "--tickers",
        *list(tickers),
        "--raw-dir",
        str(fin_paths.DATA_RAW_DIR),
        "--suffix",
        "_data.csv",
        "--out-dir",
        str(tda_out_dir),
    ]
    if prefix_map:
        tda_cmd += ["--map", *[f"{k}={v}" for k, v in prefix_map.items()]]
    if write_metrics:
        tda_cmd += ["--write-metrics"]
    if write_prompt_headers:
        tda_cmd += ["--write-prompt-header"]

    rc, out, err = _run_cmd(tda_cmd, cwd=FIN_ROOT)
    _write_text(run_dir / "TDA_STDOUT.txt", out)
    _write_text(run_dir / "TDA_STDERR.txt", err)

    if rc != 0:
        found = sorted(tda_out_dir.glob("TDA_CONTEXT_*.md"))
        if found:
            tda_md = found[-1]
        else:
            _write_text(tda_md, "TDA_CONTEXT\n\n[golden_baseline] tda_export failed; see TDA_STDERR.txt.\n")
    else:
        found = sorted(tda_out_dir.glob("TDA_CONTEXT_*.md"))
        if found:
            shutil.copy2(found[-1], tda_md)
        else:
            _write_text(tda_md, "TDA_CONTEXT\n\n[golden_baseline] tda_export succeeded but no TDA_CONTEXT_*.md found.\n")

    meta_json = run_dir / "RUN_META.json"
    meta = {
        "computed_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fin_root": str(FIN_ROOT),
        "tickers": list(tickers),
        "prefix_map": prefix_map,
        "python": sys.version,
        "executable": _python_exe(),
        "data_raw_dir": str(fin_paths.DATA_RAW_DIR),
    }
    _write_text(meta_json, json.dumps(meta, indent=2))

    return RunPaths(
        run_dir=run_dir,
        fh3_txt=fh3_txt,
        fh3_csv_full=fh3_csv_full,
        fh3_csv_min=fh3_csv_min,
        svl_md=svl_md,
        tda_md=tda_md,
        meta_json=meta_json,
    )


# ----------------------------------------------------------------------
# Comparison
# ----------------------------------------------------------------------


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _unified_diff(a: str, b: str, fromfile: str, tofile: str, n: int = 3) -> str:
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=fromfile, tofile=tofile, n=n)
    return "".join(diff)


def _normalize_volatile_lines(text: str) -> str:
    out_lines: List[str] = []
    for ln in text.splitlines():
        if re.search(r"\bcomputed_on:\s*\d{4}-\d{2}-\d{2}", ln):
            out_lines.append(re.sub(r"(computed_on:\s*).*$", r"\1<normalized>", ln))
            continue
        if re.search(r"\bdata_source:\s*CSV:", ln):
            out_lines.append(re.sub(r"(data_source:\s*CSV:).*$", r"\1<normalized_path>", ln))
            continue
        if "CSV:" in ln and ("data_source" in ln or "Data_source" in ln):
            out_lines.append(re.sub(r"CSV:.*", "CSV:<normalized_path>", ln))
            continue
        out_lines.append(ln)
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


def _compare_text_files(golden: Path, fresh: Path, *, normalize: bool = True) -> Tuple[bool, str]:
    if not golden.exists():
        return False, f"Golden file missing: {golden}"
    if not fresh.exists():
        return False, f"Fresh file missing: {fresh}"

    g = _read_text(golden)
    f = _read_text(fresh)

    if normalize:
        g = _normalize_volatile_lines(g)
        f = _normalize_volatile_lines(f)

    if g == f:
        return True, ""

    diff = _unified_diff(g, f, fromfile=str(golden), tofile=str(fresh))
    return False, diff


def _compare_csv_files(golden: Path, fresh: Path, *, float_tol: float = 1e-8) -> Tuple[bool, str]:
    if not golden.exists():
        return False, f"Golden file missing: {golden}"
    if not fresh.exists():
        return False, f"Fresh file missing: {fresh}"

    g = pd.read_csv(golden)
    f = pd.read_csv(fresh)

    if list(g.columns) != list(f.columns):
        return False, f"CSV columns differ.\nGolden: {list(g.columns)}\nFresh:  {list(f.columns)}"

    if len(g) != len(f):
        return False, f"CSV row counts differ. Golden={len(g)} Fresh={len(f)}"

    issues: List[str] = []

    for col in g.columns:
        gs0 = g[col]
        fs0 = f[col]

        # Force Series typing to keep .isna/.sub/.abs well-typed under Pylance.
        gs = cast(pd.Series, gs0)
        fs = cast(pd.Series, fs0)

        gs_num = cast(pd.Series, pd.to_numeric(gs, errors="coerce"))
        fs_num = cast(pd.Series, pd.to_numeric(fs, errors="coerce"))

        num_mask = cast(pd.Series, (~gs_num.isna()) & (~fs_num.isna()))

        if int(num_mask.sum()) >= max(1, int(0.7 * len(g))):
            # Series-typed numeric compare (prevents "float has no attribute abs/isna")
            diff_ser = cast(pd.Series, gs_num.sub(fs_num).abs())
            bad_ser = cast(pd.Series, diff_ser > float(float_tol))
            if bool(bad_ser.any()):
                bad_idx = cast(List[int], bad_ser[bad_ser].index[:10].tolist())
                issues.append(
                    f"Column '{col}' numeric mismatch (tol={float_tol}). Examples idx={bad_idx}."
                )
        else:
            gs_str = cast(pd.Series, gs.astype(str).fillna(""))
            fs_str = cast(pd.Series, fs.astype(str).fillna(""))
            bad_ser = cast(pd.Series, gs_str != fs_str)
            if bool(bad_ser.any()):
                bad_idx = cast(List[int], bad_ser[bad_ser].index[:10].tolist())
                issues.append(f"Column '{col}' string mismatch. Examples idx={bad_idx}.")

    if not issues:
        return True, ""

    return False, "\n".join(issues)


def compare_against_golden(*, run_paths: RunPaths, golden_dir: Path, float_tol: float) -> CompareResult:
    issues: List[str] = []

    g_fh3_txt = golden_dir / "FH3_STDOUT.txt"
    g_fh3_full = golden_dir / "FH3_FULL.csv"
    g_fh3_min = golden_dir / "FH3_MINIMAL.csv"
    g_svl_md = golden_dir / "SVL_CONTEXT.md"
    g_tda_md = golden_dir / "TDA_CONTEXT.md"

    ok, msg = _compare_text_files(g_fh3_txt, run_paths.fh3_txt, normalize=True)
    if not ok:
        issues.append(f"[FH3_STDOUT] Diff:\n{msg}")

    ok, msg = _compare_csv_files(g_fh3_full, run_paths.fh3_csv_full, float_tol=float_tol)
    if not ok:
        issues.append(f"[FH3_FULL.csv] {msg}")

    ok, msg = _compare_csv_files(g_fh3_min, run_paths.fh3_csv_min, float_tol=float_tol)
    if not ok:
        issues.append(f"[FH3_MINIMAL.csv] {msg}")

    ok, msg = _compare_text_files(g_svl_md, run_paths.svl_md, normalize=True)
    if not ok:
        issues.append(f"[SVL_CONTEXT] Diff:\n{msg}")

    ok, msg = _compare_text_files(g_tda_md, run_paths.tda_md, normalize=True)
    if not ok:
        issues.append(f"[TDA_CONTEXT] Diff:\n{msg}")

    return CompareResult(ok=(len(issues) == 0), issues=issues)


def update_golden_from_run(run_paths: RunPaths, golden_dir: Path) -> None:
    _ensure_dir(golden_dir)

    shutil.copy2(run_paths.fh3_txt, golden_dir / "FH3_STDOUT.txt")
    shutil.copy2(run_paths.fh3_csv_full, golden_dir / "FH3_FULL.csv")
    shutil.copy2(run_paths.fh3_csv_min, golden_dir / "FH3_MINIMAL.csv")
    shutil.copy2(run_paths.svl_md, golden_dir / "SVL_CONTEXT.md")
    shutil.copy2(run_paths.tda_md, golden_dir / "TDA_CONTEXT.md")
    shutil.copy2(run_paths.meta_json, golden_dir / "LAST_RUN_META.json")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FIN Golden Baseline Utility (generate/verify/update).")

    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
        sp.add_argument("--map", nargs="*", default=[], help="Optional logical->prefix mapping, e.g. SPX=GSPC")
        sp.add_argument("--golden-dir", type=str, default=str(DEFAULT_GOLDEN_DIR))
        sp.add_argument("--runs-dir", type=str, default=str(DEFAULT_RUNS_DIR))
        sp.add_argument("--float-tol", type=float, default=1e-8)
        sp.add_argument("--no-metrics", action="store_true", help="Do not write metrics CSVs from exporters.")
        sp.add_argument("--prompt-headers", action="store_true", help="Ask exporters to write prompt headers.")

    add_common(sub.add_parser("generate", help="Generate fresh artifacts (no compare)."))
    add_common(sub.add_parser("verify", help="Generate and compare against golden."))
    add_common(sub.add_parser("update", help="Generate and overwrite golden with the fresh artifacts."))

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    tickers = [str(t).strip() for t in args.tickers if str(t).strip()]
    if not tickers:
        raise SystemExit("No tickers provided.")

    prefix_map = _parse_map_items(args.map) if args.map else {}

    golden_dir = Path(args.golden_dir).resolve()
    runs_dir = Path(args.runs_dir).resolve()
    _ensure_dir(runs_dir)

    run_dir = (runs_dir / _now_tag()).resolve()

    write_metrics = not bool(args.no_metrics)
    write_prompt_headers = bool(args.prompt_headers)

    print(f"[golden_baseline] FIN_ROOT:   {FIN_ROOT}")
    print(f"[golden_baseline] command:    {args.command}")
    print(f"[golden_baseline] run_dir:    {run_dir}")
    print(f"[golden_baseline] golden_dir: {golden_dir}")
    print(f"[golden_baseline] tickers:    {tickers}")
    print(f"[golden_baseline] map:        {prefix_map}")

    run_paths = generate_artifacts(
        tickers=tickers,
        prefix_map=prefix_map,
        run_dir=run_dir,
        write_metrics=write_metrics,
        write_prompt_headers=write_prompt_headers,
    )

    print("[golden_baseline] Generated:")
    print(f"  {run_paths.fh3_txt}")
    print(f"  {run_paths.fh3_csv_full}")
    print(f"  {run_paths.fh3_csv_min}")
    print(f"  {run_paths.svl_md}")
    print(f"  {run_paths.tda_md}")
    print(f"  {run_paths.meta_json}")

    if args.command == "generate":
        return 0

    if args.command == "verify":
        res = compare_against_golden(run_paths=run_paths, golden_dir=golden_dir, float_tol=float(args.float_tol))
        if res.ok:
            print("[golden_baseline] VERIFY OK: fresh artifacts match golden baselines.")
            return 0

        print("[golden_baseline] VERIFY FAILED: differences detected.")
        for i, issue in enumerate(res.issues, 1):
            print(f"\n--- ISSUE {i} ---\n{issue}")
        return 2

    if args.command == "update":
        update_golden_from_run(run_paths, golden_dir)
        print("[golden_baseline] UPDATED: golden baselines overwritten from fresh run.")
        print(f"[golden_baseline] golden_dir: {golden_dir}")
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
