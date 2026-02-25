# ------------------------
# scripts\svl_export.py
# ------------------------
# SVL-v1.0 Export Utility (Fractal-only, Daily) — FIN Refactor Phase 1
#
# Purpose:
#   - Load daily OHLCV CSVs (FIN convention preferred: data/raw/tickers/{TICKER}_data.csv)
#     with transitional fallback to data/raw/{TICKER}_data.csv
#   - Compute SVL-v1.0 STRUCTURAL_CONTEXT via compat/StructuralIndicators.py
#   - Export:
#       1) Paste-ready STRUCTURAL_CONTEXT block (markdown)
#       2) Optional metrics CSV summary
#       3) Optional "browser-agent insertion" text snippet (prompt header)
#
# Default FIN paths:
#   --csv-dir  defaults to <FIN>/data/raw/tickers
#   --out-dir  defaults to <FIN>/data/artifacts/svl
#
# Example:
#   python scripts/svl_export.py --tickers TNX DJI SPX VIX QQQ AAPL --map-json "{\"SPX\":\"GSPC\"}" --print --write-metrics
#
# Notes:
# - This script is intentionally robust to working-directory differences (Phase 1).
# - Directory creation happens only after ensure_directories() is called in main().

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------
# Transitional bootstrap (Phase 1)
# ---------------------------------------------------------------------
# Allow running from anywhere: ensure FIN root is on sys.path.
_FIN_ROOT = Path(__file__).resolve().parents[1]
if str(_FIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_FIN_ROOT))

from src.config import paths  # noqa: E402

# Import SVL engine functions from compat layer (Phase 1: StructuralIndicators remains legacy-compatible)
from compat.StructuralIndicators import (  # noqa: E402
    load_ohlcv_from_csv,
    compute_structural_context_for_ticker,
    export_structural_context_markdown,
    export_metrics_csv,
)


# ----------------------------
# CLI parsing
# ----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SVL-v1.0 export utility (STRUCTURAL_CONTEXT + metrics) — FIN.")

    p.add_argument(
        "--csv-dir",
        type=str,
        default=str(paths.DATA_TICKERS_DIR),
        help="Directory containing per-ticker CSV files. Default: FIN data/raw/tickers",
    )
    p.add_argument(
        "--csv-suffix",
        type=str,
        default="_data.csv",
        help="CSV suffix (default: _data.csv). Example: _data.csv",
    )

    p.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="Logical tickers (e.g., TNX DJI SPX VIX QQQ AAPL).",
    )

    p.add_argument(
        "--map-json",
        type=str,
        default=None,
        help=(
            "Optional JSON string or JSON file path mapping logical tickers to CSV prefixes. "
            "Example: '{\"SPX\":\"GSPC\"}'"
        ),
    )

    p.add_argument(
        "--out-dir",
        type=str,
        default=str(paths.SVL_ARTIFACTS_DIR),
        help="Directory for output artifacts. Default: FIN data/artifacts/svl",
    )
    p.add_argument(
        "--basename",
        type=str,
        default="SVL",
        help="Basename prefix for generated files (default: SVL).",
    )

    p.add_argument("--write-metrics", action="store_true", help="Also write metrics CSV (recommended).")
    p.add_argument(
        "--write-prompt-header",
        action="store_true",
        help="Also write a browser-agent prompt header snippet referencing STRUCTURAL_CONTEXT.",
    )

    p.add_argument("--print", action="store_true", help="Print STRUCTURAL_CONTEXT markdown to stdout.")

    p.add_argument(
        "--method-notes",
        type=str,
        default="",
        help="Extra method notes appended to provenance in each ticker.",
    )

    return p.parse_args()


def load_mapping(map_json: Optional[str]) -> Dict[str, str]:
    if not map_json:
        return {}
    s = map_json.strip()
    path = Path(s)
    if path.exists() and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(s)


# ----------------------------
# Core workflow
# ----------------------------

def resolve_csv_path(csv_dir: Path, logical: str, mapped: str, suffix: str) -> Path:
    """
    Preferred: <mapped><suffix> then fallback: <logical><suffix>
    """
    primary = (csv_dir / f"{mapped}{suffix}").resolve()
    fallback = (csv_dir / f"{logical}{suffix}").resolve()

    candidates = [primary, fallback]
    if csv_dir.name == "tickers":
        legacy_dir = csv_dir.parent
        candidates.extend(
            [
                (legacy_dir / f"{mapped}{suffix}").resolve(),
                (legacy_dir / f"{logical}{suffix}").resolve(),
            ]
        )

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        f"CSV not found for {logical}. Tried: {', '.join(str(p) for p in candidates)}"
    )


def compute_contexts_from_csv(
    csv_dir: Path,
    tickers: List[str],
    mapping: Dict[str, str],
    csv_suffix: str,
    extra_method_notes: str = "",
):
    computed_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_method_notes = (
        "SVL-v1.0: Hurst via R/S on log(Close) windows; "
        "Trend10D thresholds ±1%; Williams 5-bar fractals confirmed up to t-2."
    )
    method_notes = base_method_notes
    if extra_method_notes.strip():
        method_notes = f"{base_method_notes} {extra_method_notes.strip()}"

    contexts = []
    asof_dates: List[pd.Timestamp] = []

    for logical in tickers:
        mapped = mapping.get(logical) or logical
        csv_path = resolve_csv_path(csv_dir, logical, mapped, csv_suffix)

        df_raw = load_ohlcv_from_csv(csv_path)

        ctx = compute_structural_context_for_ticker(
            ticker=logical,
            df_ohlcv_raw=df_raw,
            data_source=f"CSV:{csv_path}",
            computed_on=computed_on,
            method_notes=method_notes,
        )
        contexts.append(ctx)
        asof_dates.append(pd.to_datetime(ctx.asof_date))

    # Global as-of: MIN across tickers to ensure common last close
    global_asof = min(asof_dates).strftime("%Y-%m-%d") if asof_dates else datetime.now().strftime("%Y-%m-%d")
    return contexts, global_asof


def make_default_paths(out_dir: Path, basename: str, global_asof: str) -> Tuple[Path, Path, Path]:
    safe_date = global_asof.replace("-", "")
    md_path = out_dir / f"{basename}_CONTEXT_{safe_date}.md"
    csv_path = out_dir / f"{basename}_METRICS_{safe_date}.csv"
    hdr_path = out_dir / f"{basename}_PROMPT_HEADER_{safe_date}.txt"
    return md_path, csv_path, hdr_path


def build_prompt_header_snippet(context_md_filename: str) -> str:
    """
    Produces a small snippet you can paste above your AXIOM prompt.
    It instructs the browser agent to treat STRUCTURAL_CONTEXT as computed internal input.
    """
    return (
        "IMPORTANT INPUT CHANNELS\n"
        "1) WEB SOURCES: Use browsing to collect events, calendars, and factual claims. "
        "Every factual claim from the world must be cited with recent reputable sources.\n"
        "2) STRUCTURAL_CONTEXT: Computed internal diagnostics from daily OHLCV. "
        "Do not browse for fractal regimes. Do not infer structure from articles. "
        "Structural statements must be grounded only in the pasted STRUCTURAL_CONTEXT block.\n\n"
        "INSTRUCTIONS\n"
        "- Paste the entire STRUCTURAL_CONTEXT block from the generated file below into the prompt.\n"
        f"- Source file: {context_md_filename}\n"
        "- Then apply deterministic Structural Alignment and Sentiment Adjustment rules (SVL-v1.0) as previously specified.\n"
    )


def main() -> None:
    args = parse_args()

    # Explicit directory creation (Phase 1 invariant: no mkdir on import)
    paths.ensure_directories()

    csv_dir = Path(args.csv_dir)
    if not csv_dir.exists() or not csv_dir.is_dir():
        raise SystemExit(f"csv-dir does not exist or is not a directory: {csv_dir}")

    mapping = load_mapping(args.map_json)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)  # runtime side effect is allowed here (explicit in main)

    contexts, global_asof = compute_contexts_from_csv(
        csv_dir=csv_dir,
        tickers=args.tickers,
        mapping=mapping,
        csv_suffix=args.csv_suffix,
        extra_method_notes=args.method_notes,
    )

    md_text = export_structural_context_markdown(contexts, global_asof)

    md_path, csv_path, hdr_path = make_default_paths(out_dir, args.basename, global_asof)

    md_path.write_text(md_text, encoding="utf-8")

    if args.write_metrics:
        export_metrics_csv(contexts).to_csv(csv_path, index=False)

    if args.write_prompt_header:
        hdr_text = build_prompt_header_snippet(context_md_filename=md_path.name)
        hdr_path.write_text(hdr_text, encoding="utf-8")

    if args.print:
        print(md_text)

    # Minimal terminal output (non-verbose, operationally useful)
    print(f"[svl_export] Wrote: {md_path}")
    if args.write_metrics:
        print(f"[svl_export] Wrote: {csv_path}")
    if args.write_prompt_header:
        print(f"[svl_export] Wrote: {hdr_path}")


if __name__ == "__main__":
    main()
