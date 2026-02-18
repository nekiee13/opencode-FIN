# ------------------------
# scripts\tda_export.py
# ------------------------
"""
FIN — Phase 2A TDA artifact exporter (weekly / H1 cycles from return embeddings)

Responsibilities (mirrors scripts/svl_export.py philosophy)
---------------------------------------------------------
- Load per-ticker OHLCV CSVs from FIN canonical location: data/raw/{PREFIX}_data.csv
- Compute TDA Phase 2A structural context using FIN's TDA module (preferred) or legacy fallback.
- Write paste-ready markdown artifact: data/artifacts/tda/TDA_CONTEXT_<ASOF>.md (always)
- Optionally write metrics CSV:       data/artifacts/tda/TDA_METRICS_<ASOF>.csv
- Optionally write prompt header:     data/artifacts/tda/TDA_PROMPT_HEADER_<ASOF>.txt
- Graceful degradation:
    - Missing CSVs or compute failures produce degraded per-ticker entries (not a crash).
    - If ripser (or required deps) are missing, exporter still writes markdown indicating disabled states.

Execution model
---------------
This script is designed to be executed from FIN root *or* any working directory.

Typical usage
-------------
  python scripts/tda_export.py --tickers TNX DJI SPX VIX QQQ AAPL --map SPX=GSPC
  python scripts/tda_export.py --tickers QQQ AAPL --out-dir data/artifacts/tda --write-metrics --write-prompt-header

Notes
-----
- The actual TDA computation implementation is expected in one of:
    1) src.structural.tda_indicators  (preferred)
    2) TDAIndicators                 (legacy flat module)
    3) compat.TDAIndicators          (legacy namespace)
  The exporter will auto-detect whichever is importable.

- CSV loading uses src.data.loading.fetch_data(), which already normalizes dates and OHLC columns.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd


# ----------------------------
# Bootstrap imports (allow any CWD)
# ----------------------------


def _bootstrap_sys_path() -> Path:
    """
    Ensure FIN root is importable when executed from arbitrary CWDs.

    Expected location:
        FIN/scripts/tda_export.py

    Therefore:
        project_root = <this_file>/..
    """
    here = Path(__file__).resolve()
    project_root = here.parents[1]  # scripts -> FIN(root)

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    compat_dir = project_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))

    return project_root


FIN_ROOT = _bootstrap_sys_path()

# These should now be importable
from src.config import paths as fin_paths  # noqa: E402
from src.data.loading import fetch_data  # noqa: E402


# ----------------------------
# Dynamic import of TDA implementation
# ----------------------------


@dataclass(frozen=True)
class TDAModule:
    """
    A small adapter surface that normalizes whatever TDA module is available.

    Expected callable shapes:
      - compute_tda_context(ticker_dfs: Dict[str, pd.DataFrame], **kwargs) -> (contexts, md, metrics_df)
      - build_tda_context_markdown(contexts, global_asof, title=...) -> str
      - build_tda_metrics_df(contexts, global_asof) -> pd.DataFrame
    """

    compute_tda_context: Callable[..., Tuple[List[Any], str, pd.DataFrame]]
    build_tda_context_markdown: Callable[..., str]
    build_tda_metrics_df: Callable[..., pd.DataFrame]

    # Types are OPTIONAL for exporter functionality; avoid hard dependency on legacy type exports.
    # This avoids Pylance errors when compat/legacy modules do not declare these attributes.
    TDAState: Any = None
    TickerTDAContext: Any = None

    # Defaults (if module provides them; else fallback values used)
    DEFAULT_WINDOW_LEN: int = 60
    DEFAULT_EMBED_M: int = 3
    DEFAULT_EMBED_TAU: int = 1
    DEFAULT_PERSIST_THR: float = 0.5
    DEFAULT_LASTN: int = 10


def _load_tda_module() -> TDAModule:
    """
    Try the refactor module first, then legacy fallbacks.

    The loader is intentionally defensive. If the internal TDA module has
    a different API, this is the single place to reconcile it.
    """
    errors: List[str] = []

    # 1) Preferred refactor module
    try:
        from src.structural import tda_indicators as m  # type: ignore

        return TDAModule(
            compute_tda_context=m.compute_tda_context,
            build_tda_context_markdown=m.build_tda_context_markdown,
            build_tda_metrics_df=m.build_tda_metrics_df,
            # optional types (present in refactor module)
            TDAState=getattr(m, "TDAState", None),
            TickerTDAContext=getattr(m, "TickerTDAContext", None),
            # CPI-aligned defaults
            DEFAULT_WINDOW_LEN=int(getattr(m, "DEFAULT_WINDOW_LEN", 60)),
            DEFAULT_EMBED_M=int(getattr(m, "DEFAULT_EMBED_M", 3)),
            DEFAULT_EMBED_TAU=int(getattr(m, "DEFAULT_EMBED_TAU", 1)),
            DEFAULT_PERSIST_THR=float(getattr(m, "DEFAULT_PERSIST_THR", 0.5)),
            DEFAULT_LASTN=int(getattr(m, "DEFAULT_LASTN", 10)),
        )
    except Exception as e:
        errors.append(f"src.structural.tda_indicators: {type(e).__name__}: {e}")

    # 2) Legacy flat import (available via compat sys.path bootstrap)
    try:
        import TDAIndicators as m  # type: ignore

        return TDAModule(
            compute_tda_context=m.compute_tda_context,
            build_tda_context_markdown=m.build_tda_context_markdown,
            build_tda_metrics_df=m.build_tda_metrics_df,
            # optional types (may not exist; do not require)
            TDAState=getattr(m, "TDAState", None),
            TickerTDAContext=getattr(m, "TickerTDAContext", None),
            DEFAULT_WINDOW_LEN=int(getattr(m, "DEFAULT_WINDOW_LEN", 60)),
            DEFAULT_EMBED_M=int(getattr(m, "DEFAULT_EMBED_M", 3)),
            DEFAULT_EMBED_TAU=int(getattr(m, "DEFAULT_EMBED_TAU", 1)),
            DEFAULT_PERSIST_THR=float(getattr(m, "DEFAULT_PERSIST_THR", 0.5)),
            DEFAULT_LASTN=int(getattr(m, "DEFAULT_LASTN", 10)),
        )
    except Exception as e:
        errors.append(f"TDAIndicators: {type(e).__name__}: {e}")

    # 3) Legacy compat namespace
    try:
        from compat import TDAIndicators as m  # type: ignore

        return TDAModule(
            compute_tda_context=m.compute_tda_context,
            build_tda_context_markdown=m.build_tda_context_markdown,
            build_tda_metrics_df=m.build_tda_metrics_df,
            # optional types (may not exist; do not require)
            TDAState=getattr(m, "TDAState", None),
            TickerTDAContext=getattr(m, "TickerTDAContext", None),
            DEFAULT_WINDOW_LEN=int(getattr(m, "DEFAULT_WINDOW_LEN", 60)),
            DEFAULT_EMBED_M=int(getattr(m, "DEFAULT_EMBED_M", 3)),
            DEFAULT_EMBED_TAU=int(getattr(m, "DEFAULT_EMBED_TAU", 1)),
            DEFAULT_PERSIST_THR=float(getattr(m, "DEFAULT_PERSIST_THR", 0.5)),
            DEFAULT_LASTN=int(getattr(m, "DEFAULT_LASTN", 10)),
        )
    except Exception as e:
        errors.append(f"compat.TDAIndicators: {type(e).__name__}: {e}")

    raise RuntimeError(
        "Unable to import any TDA module implementation. Tried:\n  - "
        + "\n  - ".join(errors)
        + "\n\nResolution: ensure src/structural/tda_indicators.py exports the expected functions "
        "(compute_tda_context, build_tda_context_markdown, build_tda_metrics_df)."
    )


# ----------------------------
# Export structures
# ----------------------------


@dataclass(frozen=True)
class ExportPaths:
    context_md: Path
    metrics_csv: Optional[Path]
    prompt_header: Optional[Path]


# ----------------------------
# Helpers: mapping + file resolution
# ----------------------------


def parse_prefix_map(items: List[str]) -> Dict[str, str]:
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


def resolve_csv_path(
    ticker: str,
    *,
    prefix_map: Optional[Dict[str, str]],
    raw_dir: Path,
    suffix: str,
) -> Path:
    prefix = prefix_map.get(ticker, ticker) if prefix_map else ticker
    prefix = str(prefix).replace("^", "")
    return (raw_dir / f"{prefix}{suffix}").resolve()


def _asof_tag(ts: pd.Timestamp, fmt: str = "%Y%m%d") -> str:
    return pd.Timestamp(ts).strftime(fmt)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ----------------------------
# Core exporter
# ----------------------------


def export_tda_artifacts(
    tickers: List[str],
    *,
    out_dir: Optional[Path] = None,
    raw_dir: Optional[Path] = None,
    suffix: str = "_data.csv",
    prefix_map: Optional[Dict[str, str]] = None,
    write_metrics_csv: bool = True,
    write_prompt_header: bool = False,
    asof_policy: str = "min_across_tickers",
    asof_fmt: str = "%Y%m%d",
    window_len: int = 60,
    embed_m: int = 3,
    embed_tau: int = 1,
    persist_thr: float = 0.5,
    lastn: int = 10,
) -> ExportPaths:
    """
    Export Phase 2A TDA artifacts.

    Always writes:
      - TDA_CONTEXT_<ASOF>.md

    Optionally writes:
      - TDA_METRICS_<ASOF>.csv
      - TDA_PROMPT_HEADER_<ASOF>.txt
    """
    tda = _load_tda_module()

    # Align CLI defaults to module defaults unless explicitly overridden
    if window_len == 60 and int(tda.DEFAULT_WINDOW_LEN) != 60:
        window_len = int(tda.DEFAULT_WINDOW_LEN)
    if embed_m == 3 and int(tda.DEFAULT_EMBED_M) != 3:
        embed_m = int(tda.DEFAULT_EMBED_M)
    if embed_tau == 1 and int(tda.DEFAULT_EMBED_TAU) != 1:
        embed_tau = int(tda.DEFAULT_EMBED_TAU)
    if abs(persist_thr - 0.5) < 1e-12 and float(tda.DEFAULT_PERSIST_THR) != 0.5:
        persist_thr = float(tda.DEFAULT_PERSIST_THR)
    if lastn == 10 and int(tda.DEFAULT_LASTN) != 10:
        lastn = int(tda.DEFAULT_LASTN)

    out_dir = (out_dir or fin_paths.TDA_ARTIFACTS_DIR).resolve()
    raw_dir = (raw_dir or fin_paths.DATA_RAW_DIR).resolve()

    # Load CSVs via canonical FIN loader
    ticker_dfs: Dict[str, pd.DataFrame] = {}
    ticker_errors: Dict[str, str] = {}

    for t in tickers:
        csv_path = resolve_csv_path(
            t, prefix_map=prefix_map, raw_dir=raw_dir, suffix=suffix
        )
        try:
            df = fetch_data(t, csv_path=csv_path)
        except Exception as e:
            ticker_errors[t] = f"Load failed: {type(e).__name__}: {e} ({csv_path})"
            continue
        if df is None or df.empty:
            ticker_errors[t] = f"Load failed or empty after cleaning: {csv_path}"
            continue
        if "Close" not in df.columns:
            ticker_errors[t] = (
                f"Missing Close column after cleaning: {csv_path} (cols={list(df.columns)})"
            )
            continue
        ticker_dfs[t] = df.copy()

    contexts_loaded: List[Any] = []
    if ticker_dfs:
        try:
            contexts_loaded, _, _ = tda.compute_tda_context(
                ticker_dfs,
                asof_policy=asof_policy,
                window_len=window_len,
                embed_m=embed_m,
                embed_tau=embed_tau,
                persist_thr=persist_thr,
                lastn=lastn,
            )
        except Exception as e:
            tb = traceback.format_exc()
            for t in ticker_dfs.keys():
                ticker_errors[t] = (
                    f"TDA compute_tda_context failed: {type(e).__name__}: {e}"
                )
            ticker_errors["__TDA_GLOBAL__"] = tb
            contexts_loaded = []

    # Determine global asof for filenames (deterministic; CPI default is min across tickers)
    if contexts_loaded:
        try:
            global_asof = min(pd.Timestamp(getattr(c, "asof")) for c in contexts_loaded)
        except Exception:
            global_asof = (
                min(pd.Timestamp(df.index.max()) for df in ticker_dfs.values())
                if ticker_dfs
                else pd.Timestamp("1970-01-01")
            )
    elif ticker_dfs:
        global_asof = min(pd.Timestamp(df.index.max()) for df in ticker_dfs.values())
    else:
        global_asof = pd.Timestamp("1970-01-01")

    # Add degraded contexts for tickers that failed to load (or compute)
    contexts_all: List[Any] = list(contexts_loaded)

    # Prefer CPI state names, fallback safely if legacy enum differs.
    degraded_state = None
    if tda.TDAState is not None:
        degraded_state = (
            getattr(tda.TDAState, "INSUFFICIENT_DATA", None)
            or getattr(tda.TDAState, "MISSING_DEP", None)
            or getattr(tda.TDAState, "DEGENERATE", None)
            or getattr(tda.TDAState, "ERROR", None)
            or getattr(tda.TDAState, "DISABLED", None)
            or getattr(tda.TDAState, "FAILED", None)
        )
    if degraded_state is None:
        degraded_state = "INSUFFICIENT_DATA"

    for t, err in ticker_errors.items():
        if t == "__TDA_GLOBAL__":
            continue
        try:
            # Use module implementation for degraded rows when possible:
            # Passing an empty DF triggers a stable INSUFFICIENT_DATA outcome and ensures CPI columns exist.
            empty = pd.DataFrame({"Close": pd.Series(dtype=float)})
            ctxs_one, _, _ = tda.compute_tda_context(
                {t: empty},
                asof_policy="per_ticker",
                window_len=window_len,
                embed_m=embed_m,
                embed_tau=embed_tau,
                persist_thr=persist_thr,
                lastn=lastn,
            )
            if ctxs_one:
                ctx = ctxs_one[0]
                try:
                    ctx.asof = pd.Timestamp(global_asof)  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    ctx.notes.append(err)  # type: ignore[attr-defined]
                except Exception:
                    pass
                contexts_all.append(ctx)
                continue
        except Exception:
            pass

        # Fallback degraded record: minimal dict-like object is not supported by renderers, so
        # create context only if type is available; otherwise skip (should not occur with refactor module).
        if tda.TickerTDAContext is not None:
            try:
                ctx = tda.TickerTDAContext(
                    ticker=t,
                    asof=pd.Timestamp(global_asof),
                    window_len=window_len,
                    embed_m=embed_m,
                    embed_tau=embed_tau,
                    persist_thr=persist_thr,
                    lastn=lastn,
                    state=degraded_state,
                )
                try:
                    ctx.notes.append(err)  # type: ignore[attr-defined]
                except Exception:
                    pass
                contexts_all.append(ctx)
            except Exception:
                pass

    # Stable ordering
    try:
        contexts_all.sort(key=lambda c: str(getattr(c, "ticker", "")))
    except Exception:
        pass

    title = "TDA_CONTEXT (Phase 2A — H1 cycles from return embeddings)"
    md = tda.build_tda_context_markdown(
        contexts_all, global_asof=global_asof, title=title
    )
    metrics_df = tda.build_tda_metrics_df(contexts_all, global_asof=global_asof)

    # Write files
    tag = _asof_tag(global_asof, fmt=asof_fmt)
    context_path = out_dir / f"TDA_CONTEXT_{tag}.md"
    _write_text(context_path, md)

    metrics_path: Optional[Path] = None
    if write_metrics_csv:
        metrics_path = out_dir / f"TDA_METRICS_{tag}.csv"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_df.to_csv(metrics_path, index=False, encoding="utf-8")

    prompt_header_path: Optional[Path] = None
    if write_prompt_header:
        prompt_header_path = out_dir / f"TDA_PROMPT_HEADER_{tag}.txt"
        header = (
            "IMPORTANT INPUT CHANNELS\n"
            "1) WEB SOURCES: Use browsing to collect events, calendars, and factual claims. Every factual claim must be cited.\n"
            "2) TDA_CONTEXT: Computed internal TDA diagnostics. Do not browse for TDA structure. Do not infer TDA from articles.\n\n"
            "INSTRUCTIONS\n"
            "- Paste the entire TDA_CONTEXT block from the generated file below into the prompt.\n"
            f"- Source file: {context_path.name}\n"
        )
        _write_text(prompt_header_path, header)

    return ExportPaths(
        context_md=context_path,
        metrics_csv=metrics_path,
        prompt_header=prompt_header_path,
    )


# ----------------------------
# CLI
# ----------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="FIN Phase 2A TDA exporter (TDA_CONTEXT + optional metrics)."
    )

    p.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="Logical tickers (e.g., TNX DJI SPX VIX QQQ AAPL).",
    )

    p.add_argument(
        "--map",
        nargs="*",
        default=[],
        help="Optional logical->file-prefix mappings, e.g. --map SPX=GSPC",
    )

    p.add_argument(
        "--raw-dir",
        type=str,
        default=None,
        help="Override raw data directory. Default: FIN data/raw.",
    )
    p.add_argument(
        "--suffix",
        type=str,
        default="_data.csv",
        help="CSV filename suffix (default: _data.csv).",
    )

    p.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for artifacts. Default: FIN data/artifacts/tda.",
    )

    p.add_argument(
        "--write-metrics", action="store_true", help="Write TDA_METRICS_<ASOF>.csv."
    )
    p.add_argument(
        "--write-prompt-header",
        action="store_true",
        help="Write TDA_PROMPT_HEADER_<ASOF>.txt.",
    )

    p.add_argument(
        "--asof-policy",
        default="min_across_tickers",
        choices=["min_across_tickers", "per_ticker"],
    )

    # IMPORTANT: Do NOT include literal %Y/%m/%d in argparse help text; argparse formats help via old-style '%'.
    p.add_argument(
        "--asof-fmt",
        default="%Y%m%d",
        help="ASOF tag format for filenames (strftime-style). Default example: YYYYMMDD.",
    )

    # Phase 2A params (CPI-aligned defaults; exporter will align with module defaults if different)
    p.add_argument("--window-len", type=int, default=60)
    p.add_argument("--embed-m", type=int, default=3)
    p.add_argument("--embed-tau", type=int, default=1)
    p.add_argument("--persist-thr", type=float, default=0.5)
    p.add_argument("--lastn", type=int, default=10)

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    prefix_map = parse_prefix_map(args.map) if args.map else None
    out_dir = (
        Path(args.out_dir).resolve() if args.out_dir else fin_paths.TDA_ARTIFACTS_DIR
    )
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else fin_paths.DATA_RAW_DIR

    computed_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[tda_export] FIN root: {fin_paths.APP_ROOT}")
    print(f"[tda_export] computed_on: {computed_on}")
    print(f"[tda_export] raw_dir: {raw_dir}")
    print(f"[tda_export] out_dir: {out_dir}")

    paths_out = export_tda_artifacts(
        tickers=list(args.tickers),
        out_dir=out_dir,
        raw_dir=raw_dir,
        suffix=args.suffix,
        prefix_map=prefix_map,
        write_metrics_csv=bool(args.write_metrics),
        write_prompt_header=bool(args.write_prompt_header),
        asof_policy=args.asof_policy,
        asof_fmt=args.asof_fmt,
        window_len=int(args.window_len),
        embed_m=int(args.embed_m),
        embed_tau=int(args.embed_tau),
        persist_thr=float(args.persist_thr),
        lastn=int(args.lastn),
    )

    print("[tda_export] Wrote:")
    print(f"  {paths_out.context_md}")
    if paths_out.metrics_csv:
        print(f"  {paths_out.metrics_csv}")
    if paths_out.prompt_header:
        print(f"  {paths_out.prompt_header}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
