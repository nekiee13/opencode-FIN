# ------------------------
# tools/lstm_backtest.py
# ------------------------
"""
FIN — LSTM point-forecast backtest & baseline harness.

Purpose
-------
Replay a range of "as-of" dates, run the *unmodified* canonical LSTM for each
(ticker, as-of) pair, and score the fh-step point forecast against realized
actuals. Produces a versioned baseline report so later calibration work (median
head, returns-space modeling) can be measured against a clean "before".

Design (see docs/lstm_calibration/00_backtest_baseline_plan.md)
--------------------------------------------------------------
- Entrypoint scored is the canonical production path:
  ``src.models.compat_api.predict_lstm`` (delegates to the torch LSTM). We score
  exactly what production runs — no re-implementation.
- Leakage guard: training history comes from ``fetch_data(ticker, as_of_date=as_of)``
  which filters ``index <= as_of``. Actuals come from a separate full-history load.
  The harness asserts ``max(train) <= as_of < min(forecast_date)`` defensively.
- Forecast horizon is read from ``Constants.FH`` (the model does not accept an fh
  argument); ``--fh`` overrides it by setting the Constants attribute before calls.
- ``history_mode="replay"`` is used because a backtest *is* a replay (relaxed
  training policy for short early histories).

Determinism
-----------
``predict_lstm`` fixes the model seed at 42 internally, so model outputs are
deterministic on CPU given fixed input CSVs. The ``--seed`` flag here only seeds
the harness/NumPy for metadata reproducibility; it cannot change the model seed
without editing ``src/`` (out of scope for this epic). All aggregate metrics are
pure functions of the per-point rows.

This is a developer/baseline utility (``tools/``); no production code imports it,
so it cannot affect the compat/facade contract.

Usage
-----
    python tools/lstm_backtest.py --help
    python tools/lstm_backtest.py --tickers AAPL,QQQ --start 2025-01-01 --end 2025-04-01
    python tools/lstm_backtest.py            # all discovered tickers, derived window
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


HARNESS_VERSION = "1.0.0"
COVERAGE_TARGET = 86.0  # central PI coverage target (README PI harmonization)
DEFAULT_WINDOW_BDAYS = 60  # default count of as-of business days when --start omitted
DEFAULT_STEP = 5  # default as-of stride (weekly) to keep baseline runtime sane


# ----------------------------------------------------------------------
# Repo-root bootstrap (CWD-robust, mirrors tools/import_audit.py)
# ----------------------------------------------------------------------
def _bootstrap_fin_root() -> Path:
    """Insert the FIN repo root (and compat/) onto sys.path and return the root.

    ``compat/`` is added so the legacy top-level ``import Constants`` used inside
    ``src/models/intervals.py::_discover`` resolves to ``compat/Constants.py``.
    Without it, PI settings silently fall back to defaults (0.90 / q0.05 / q0.95)
    instead of the harmonized target (0.86 / q0.07 / q0.93), which would skew the
    interval-coverage diagnostics in the baseline. This mirrors how production
    entrypoints make Constants importable.
    """
    here = Path(__file__).resolve()
    root: Optional[Path] = None
    for p in (here.parent, *here.parents):
        if (p / "src").exists() and (p / "config").exists():
            root = p
            break
    if root is None:
        root = here.parents[1]
    for entry in (root, root / "compat"):
        if entry.exists() and str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    return root


FIN_ROOT = _bootstrap_fin_root()

# Local imports must follow the bootstrap so `src`/`compat` resolve from any CWD.
import compat.Constants as C  # noqa: E402
from src.config import paths  # noqa: E402
from src.data.loading import fetch_data  # noqa: E402
from src.models.compat_api import predict_lstm  # noqa: E402


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class BacktestConfig:
    tickers: Sequence[str]
    start: Optional[str]
    end: Optional[str]
    step: int
    fh: int
    history_mode: str
    seed: int
    out_dir: Path
    skip_threshold: float  # fraction; baseline flagged if skip_rate exceeds this


# ----------------------------------------------------------------------
# Discovery helpers
# ----------------------------------------------------------------------
def discover_tickers(suffix: str = "_data.csv") -> List[str]:
    """Return ticker symbols found under the canonical raw tickers dir."""
    tdir = paths.DATA_TICKERS_DIR
    if not tdir.exists():
        return []
    names = sorted(
        p.name[: -len(suffix)] for p in tdir.glob(f"*{suffix}") if p.is_file()
    )
    return names


def load_actuals_close(ticker: str) -> Optional[pd.Series]:
    """Full-history realized Close (no as-of filter), indexed by date.

    This is the independent actuals source: it is loaded WITHOUT ``as_of_date`` so
    it can supply realized values strictly *after* each as-of cutoff. Because it is
    read separately from the truncated training frame, it cannot leak into training.
    """
    df = fetch_data(ticker)
    if df is None or "Close" not in df.columns or df.empty:
        return None
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    return close if not close.empty else None


# ----------------------------------------------------------------------
# Per-point scoring
# ----------------------------------------------------------------------
def _sign(x: float) -> int:
    return (x > 0.0) - (x < 0.0)


def _row_template(cfg: BacktestConfig, ticker: str, as_of: pd.Timestamp) -> Dict[str, Any]:
    """A report row pre-filled with run/identity columns; metric fields blank."""
    return {
        "run_id": None,  # filled at write time
        "harness_version": HARNESS_VERSION,
        "seed": cfg.seed,
        "torch_version": None,  # filled at write time
        "numpy_version": np.__version__,
        "ticker": ticker,
        "as_of_date": as_of.strftime("%Y-%m-%d"),
        "history_mode": cfg.history_mode,
        "fh": cfg.fh,
        "horizon_step": None,
        "forecast_date": None,
        "last_close": None,
        "pred": None,
        "lower": None,
        "upper": None,
        "actual": None,
        "signed_err": None,
        "abs_err": None,
        "sq_err": None,
        "ape": None,
        "smape_term": None,
        "in_interval": None,
        "interval_width": None,
        "norm_width": None,
        "dir_pred": None,
        "dir_actual": None,
        "dir_eligible": None,
        "dir_hit": None,
        "status": "scored",
        "skip_reason": None,
        "device": None,
        "model_meta_json": None,
    }


def _skip_row(
    cfg: BacktestConfig,
    ticker: str,
    as_of: pd.Timestamp,
    reason: str,
    *,
    horizon_step: Optional[int] = None,
    forecast_date: Optional[pd.Timestamp] = None,
) -> Dict[str, Any]:
    row = _row_template(cfg, ticker, as_of)
    row["status"] = "skipped"
    row["skip_reason"] = reason
    if horizon_step is not None:
        row["horizon_step"] = horizon_step
    if forecast_date is not None:
        row["forecast_date"] = forecast_date.strftime("%Y-%m-%d")
    return row


def _score_step(
    base: Dict[str, Any],
    *,
    horizon_step: int,
    forecast_date: pd.Timestamp,
    last_close: float,
    pred: float,
    lower: float,
    upper: float,
    actual: float,
) -> Dict[str, Any]:
    """Compute all per-point metric fields (formulas locked in Task 1.2)."""
    row = dict(base)
    e = float(pred) - float(actual)  # error = pred - actual (positive => over-predict)
    width = float(upper) - float(lower)

    row["horizon_step"] = int(horizon_step)
    row["forecast_date"] = forecast_date.strftime("%Y-%m-%d")
    row["last_close"] = float(last_close)
    row["pred"] = float(pred)
    row["lower"] = float(lower)
    row["upper"] = float(upper)
    row["actual"] = float(actual)
    row["signed_err"] = e
    row["abs_err"] = abs(e)
    row["sq_err"] = e * e
    row["ape"] = abs(e) / abs(actual) if actual != 0.0 else np.nan
    denom = abs(pred) + abs(actual)
    row["smape_term"] = (2.0 * abs(e) / denom) if denom != 0.0 else np.nan
    row["in_interval"] = int(lower <= actual <= upper)
    row["interval_width"] = width
    row["norm_width"] = width / last_close if last_close != 0.0 else np.nan
    dp, da = _sign(pred - last_close), _sign(actual - last_close)
    row["dir_pred"] = dp
    row["dir_actual"] = da
    row["dir_eligible"] = int(da != 0)
    row["dir_hit"] = int(dp == da) if da != 0 else None
    return row


# ----------------------------------------------------------------------
# Single (ticker, as-of) evaluation
# ----------------------------------------------------------------------
def run_one(
    cfg: BacktestConfig,
    ticker: str,
    as_of: pd.Timestamp,
    actuals: pd.Series,
) -> List[Dict[str, Any]]:
    """Run the LSTM for one (ticker, as-of) and return scored/skipped rows.

    Boundary-level exception handling: any failure is converted into a skip row so
    a single bad case logs and continues rather than aborting the whole sweep.
    """
    try:
        enriched = fetch_data(ticker, as_of_date=as_of)
        if enriched is None or "Close" not in enriched.columns or enriched.empty:
            return [_skip_row(cfg, ticker, as_of, "no_history")]

        # Leakage assert: nothing in the training frame may post-date the cutoff.
        train_max = pd.Timestamp(enriched.index.max())
        if train_max > as_of:
            raise AssertionError(
                f"leakage: train_max {train_max} > as_of {as_of} for {ticker}"
            )

        last_close = float(pd.to_numeric(enriched["Close"], errors="coerce").dropna().iloc[-1])

        out = predict_lstm(
            enriched,
            ticker=ticker,
            exo_config=None,  # clean, exog-free baseline
            history_mode=cfg.history_mode,
        )
        if out is None or getattr(out, "empty", True):
            return [_skip_row(cfg, ticker, as_of, "model_none")]

        device = None
        meta_json = None  # predict_lstm returns only the frame; meta stays minimal here

        base = _row_template(cfg, ticker, as_of)
        base["last_close"] = last_close
        base["device"] = device
        base["model_meta_json"] = meta_json

        rows: List[Dict[str, Any]] = []
        for step_idx, (fdate, fr) in enumerate(out.iterrows(), start=1):
            fdate_ts = pd.Timestamp(fdate)
            # Leakage assert: forecast dates must be strictly after the cutoff.
            if fdate_ts <= as_of:
                raise AssertionError(
                    f"leakage: forecast_date {fdate_ts} <= as_of {as_of} for {ticker}"
                )

            pred = fr.get("LSTM_Pred")
            lower = fr.get("LSTM_Lower")
            upper = fr.get("LSTM_Upper")
            if not all(np.isfinite([pred, lower, upper])):
                rows.append(
                    _skip_row(cfg, ticker, as_of, "nan_pred",
                              horizon_step=step_idx, forecast_date=fdate_ts)
                )
                continue

            # Exact-date actual lookup; holidays / unrealized dates => skip this step.
            if fdate_ts not in actuals.index:
                rows.append(
                    _skip_row(cfg, ticker, as_of, "no_actual",
                              horizon_step=step_idx, forecast_date=fdate_ts)
                )
                continue

            actual = float(actuals.loc[fdate_ts])
            rows.append(
                _score_step(
                    base,
                    horizon_step=step_idx,
                    forecast_date=fdate_ts,
                    last_close=last_close,
                    pred=float(pred),
                    lower=float(lower),
                    upper=float(upper),
                    actual=actual,
                )
            )
        return rows

    except Exception as exc:  # boundary: never abort the sweep on one case
        row = _skip_row(cfg, ticker, as_of, f"error:{type(exc).__name__}")
        row["model_meta_json"] = json.dumps({"error": str(exc)})
        return [row]


# ----------------------------------------------------------------------
# Aggregation (pure functions over scored rows)
# ----------------------------------------------------------------------
def _metric_block(df: pd.DataFrame) -> Dict[str, Any]:
    """Aggregate metrics for a subset of *scored* rows. Empty -> Nones."""
    n = int(len(df))
    if n == 0:
        return {"N": 0}
    abs_err = df["abs_err"].to_numpy(dtype=float)
    sq_err = df["sq_err"].to_numpy(dtype=float)
    signed = df["signed_err"].to_numpy(dtype=float)
    ape = df["ape"].to_numpy(dtype=float)
    smape = df["smape_term"].to_numpy(dtype=float)
    in_iv = df["in_interval"].to_numpy(dtype=float)
    width = df["interval_width"].to_numpy(dtype=float)
    nwidth = df["norm_width"].to_numpy(dtype=float)

    dir_elig = df[df["dir_eligible"] == 1]
    dir_hit = dir_elig["dir_hit"].to_numpy(dtype=float) if len(dir_elig) else np.array([])

    def _nanmean(a: np.ndarray) -> Optional[float]:
        a = a[np.isfinite(a)]
        return float(a.mean()) if a.size else None

    return {
        "N": n,
        "MAE": _nanmean(abs_err),
        "RMSE": float(np.sqrt(np.nanmean(sq_err))) if n else None,
        "MBE": _nanmean(signed),
        "MedAE": float(np.nanmedian(abs_err)) if n else None,
        "MAPE": (_nanmean(ape) * 100.0) if _nanmean(ape) is not None else None,
        "sMAPE": (_nanmean(smape) * 100.0) if _nanmean(smape) is not None else None,
        "mape_excluded_points": int(np.count_nonzero(~np.isfinite(ape))),
        "dir_hit_rate": (float(dir_hit.mean()) * 100.0) if dir_hit.size else None,
        "coverage_pct": _nanmean(in_iv) * 100.0 if _nanmean(in_iv) is not None else None,
        "mean_interval_width": _nanmean(width),
        "mean_norm_width": _nanmean(nwidth),
    }


def aggregate(rows: List[Dict[str, Any]], cfg: BacktestConfig) -> Dict[str, Any]:
    """Build the summary.json structure from all rows."""
    df = pd.DataFrame(rows)
    scored = df[df["status"] == "scored"].copy()
    skipped = df[df["status"] == "skipped"].copy()

    n_scored = int(len(scored))
    n_skipped = int(len(skipped))
    total = n_scored + n_skipped
    skip_rate = (n_skipped / total) if total else 0.0

    overall = _metric_block(scored)
    overall.update(
        {
            "N_scored": n_scored,
            "N_skipped": n_skipped,
            "skip_rate": skip_rate,
            "coverage_target": COVERAGE_TARGET,
        }
    )

    per_horizon = []
    if n_scored:
        for h, sub in scored.groupby("horizon_step"):
            block = _metric_block(sub)
            block["horizon_step"] = int(h)
            per_horizon.append(block)
        per_horizon.sort(key=lambda b: b["horizon_step"])

    per_ticker = []
    if n_scored:
        for tk, sub in scored.groupby("ticker"):
            block = _metric_block(sub)
            block["ticker"] = str(tk)
            per_ticker.append(block)
        per_ticker.sort(key=lambda b: b["ticker"])

    skips = {
        reason: int(cnt)
        for reason, cnt in skipped["skip_reason"].value_counts().items()
    } if n_skipped else {}

    return {
        "run": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_version": HARNESS_VERSION,
            "seed": cfg.seed,
            "history_mode": cfg.history_mode,
            "tickers": list(cfg.tickers),
            "start": cfg.start,
            "end": cfg.end,
            "step": cfg.step,
            "fh": cfg.fh,
            "numpy_version": np.__version__,
            "torch_version": _torch_version(),
        },
        "overall": overall,
        "per_horizon": per_horizon,
        "per_ticker": per_ticker,
        "skips": skips,
        "skip_threshold": cfg.skip_threshold,
        "skip_threshold_exceeded": skip_rate > cfg.skip_threshold,
    }


def _torch_version() -> Optional[str]:
    try:
        import torch  # type: ignore

        return str(torch.__version__)
    except Exception:
        return None


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------
def render_markdown(summary: Dict[str, Any]) -> str:
    run = summary["run"]
    ov = summary["overall"]

    def fmt(v: Any, p: str = ".4f") -> str:
        return format(v, p) if isinstance(v, (int, float)) and v is not None else "—"

    lines: List[str] = []
    lines.append("# LSTM Backtest Baseline")
    lines.append("")
    lines.append(f"- Tool version: `{run['tool_version']}`  |  torch: `{run['torch_version']}`")
    lines.append(f"- Tickers: {', '.join(run['tickers'])}")
    lines.append(f"- As-of window: {run['start']} → {run['end']} (step {run['step']}), fh={run['fh']}")
    lines.append(f"- history_mode: `{run['history_mode']}`  |  seed: {run['seed']}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- Scored: **{ov['N_scored']}**  |  Skipped: **{ov['N_skipped']}**  |  Skip rate: **{ov['skip_rate']*100:.1f}%**")
    lines.append(f"- MAE: **{fmt(ov.get('MAE'))}**  |  RMSE: **{fmt(ov.get('RMSE'))}**  |  MBE (bias): **{fmt(ov.get('MBE'))}**")
    lines.append(f"- MedAE: {fmt(ov.get('MedAE'))}  |  MAPE: {fmt(ov.get('MAPE'), '.2f')}%  |  sMAPE: {fmt(ov.get('sMAPE'), '.2f')}%")
    lines.append(f"- Directional hit-rate: {fmt(ov.get('dir_hit_rate'), '.1f')}%")
    lines.append(f"- Coverage: {fmt(ov.get('coverage_pct'), '.1f')}% (target {ov['coverage_target']}%)  |  mean width: {fmt(ov.get('mean_interval_width'))}")
    if summary.get("skip_threshold_exceeded"):
        lines.append("")
        lines.append(f"> ⚠️ **Skip rate exceeds threshold ({summary['skip_threshold']*100:.0f}%) — baseline NOT valid.**")
    lines.append("")
    lines.append("## Per-horizon (the Phase A vs B signal)")
    lines.append("")
    lines.append("| h | N | MAE | RMSE | MBE | dir hit % | coverage % |")
    lines.append("|---|---|-----|------|-----|-----------|------------|")
    for b in summary["per_horizon"]:
        lines.append(
            f"| {b['horizon_step']} | {b['N']} | {fmt(b.get('MAE'))} | {fmt(b.get('RMSE'))} | "
            f"{fmt(b.get('MBE'))} | {fmt(b.get('dir_hit_rate'), '.1f')} | {fmt(b.get('coverage_pct'), '.1f')} |"
        )
    lines.append("")
    lines.append("## Per-ticker")
    lines.append("")
    lines.append("| ticker | N | MAE | RMSE | MBE | dir hit % | coverage % |")
    lines.append("|--------|---|-----|------|-----|-----------|------------|")
    for b in summary["per_ticker"]:
        lines.append(
            f"| {b['ticker']} | {b['N']} | {fmt(b.get('MAE'))} | {fmt(b.get('RMSE'))} | "
            f"{fmt(b.get('MBE'))} | {fmt(b.get('dir_hit_rate'), '.1f')} | {fmt(b.get('coverage_pct'), '.1f')} |"
        )
    lines.append("")
    if summary["skips"]:
        lines.append("## Skips by reason")
        lines.append("")
        for reason, cnt in sorted(summary["skips"].items()):
            lines.append(f"- `{reason}`: {cnt}")
        lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# As-of window resolution
# ----------------------------------------------------------------------
def resolve_as_of_dates(
    cfg: BacktestConfig, actuals_by_ticker: Dict[str, pd.Series]
) -> List[pd.Timestamp]:
    """Build the stepped business-day as-of list, deriving defaults from data.

    Default end = (min last-actual-date across tickers) − fh business days, so the
    final forecast still has actuals. Default start = end − window business days.
    """
    last_dates = [s.index.max() for s in actuals_by_ticker.values() if s is not None and len(s)]
    if not last_dates:
        return []
    data_end = min(pd.Timestamp(d) for d in last_dates)

    end = pd.Timestamp(cfg.end) if cfg.end else (data_end - pd.tseries.offsets.BDay(cfg.fh))
    start = pd.Timestamp(cfg.start) if cfg.start else (end - pd.tseries.offsets.BDay(DEFAULT_WINDOW_BDAYS))
    if start > end:
        return []
    candidates = pd.bdate_range(start=start, end=end)
    step = max(1, int(cfg.step))
    return list(candidates[::step])


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def _parse_args(argv: Optional[Sequence[str]] = None) -> BacktestConfig:
    parser = argparse.ArgumentParser(
        description="LSTM point-forecast backtest & baseline harness (tools/lstm_backtest.py).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated tickers. Default: all discovered under data/raw/tickers.")
    parser.add_argument("--start", type=str, default=None,
                        help="First as-of date (YYYY-MM-DD). Default: end - window business days.")
    parser.add_argument("--end", type=str, default=None,
                        help="Last as-of date (YYYY-MM-DD). Default: (min last data date) - fh business days.")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP,
                        help="As-of stride in business days (1 = every business day).")
    parser.add_argument("--fh", type=int, default=int(getattr(C, "FH", 3)),
                        help="Forecast horizon (overrides Constants.FH for this run).")
    parser.add_argument("--history-mode", type=str, default="replay",
                        choices=["replay", "live"],
                        help="Training policy mode passed to predict_lstm.")
    parser.add_argument("--seed", type=int, default=42,
                        help="Harness/NumPy seed (model seed is fixed at 42 internally).")
    parser.add_argument("--out", type=str, default=str(paths.APP_ROOT / "CSV_OUTPUT" / "lstm_baseline"),
                        help="Output directory root; a timestamped subfolder is created.")
    parser.add_argument("--skip-threshold", type=float, default=0.10,
                        help="Max acceptable skip rate before the baseline is flagged invalid.")
    args = parser.parse_args(argv)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        tickers = discover_tickers()

    return BacktestConfig(
        tickers=tickers,
        start=args.start,
        end=args.end,
        step=int(args.step),
        fh=int(args.fh),
        history_mode=str(args.history_mode),
        seed=int(args.seed),
        out_dir=Path(args.out),
        skip_threshold=float(args.skip_threshold),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = _parse_args(argv)
    if not cfg.tickers:
        print("No tickers found/specified (looked under data/raw/tickers).", file=sys.stderr)
        return 2

    np.random.seed(cfg.seed)
    # Honor --fh by setting the Constants attribute the model reads (C.FH).
    if int(cfg.fh) != int(getattr(C, "FH", 3)):
        C.FH = int(cfg.fh)

    # Load actuals once per ticker (full history, no as-of filter).
    actuals_by_ticker: Dict[str, pd.Series] = {}
    for tk in cfg.tickers:
        s = load_actuals_close(tk)
        if s is not None:
            actuals_by_ticker[tk] = s
        else:
            print(f"[warn] no actuals for {tk}; it will be skipped.", file=sys.stderr)

    as_of_dates = resolve_as_of_dates(cfg, actuals_by_ticker)
    if not as_of_dates:
        print("Could not resolve any as-of dates from the given window/data.", file=sys.stderr)
        return 2

    print(
        f"[info] {len(cfg.tickers)} ticker(s) x {len(as_of_dates)} as-of date(s) "
        f"= {len(cfg.tickers) * len(as_of_dates)} model run(s); fh={cfg.fh}, step={cfg.step}.",
        file=sys.stderr,
    )

    all_rows: List[Dict[str, Any]] = []
    for tk in cfg.tickers:
        actuals = actuals_by_ticker.get(tk)
        if actuals is None:
            for a in as_of_dates:
                all_rows.append(_skip_row(cfg, tk, a, "no_actual"))
            continue
        for a in as_of_dates:
            all_rows.extend(run_one(cfg, tk, a, actuals))

    summary = aggregate(all_rows, cfg)

    # Write artifacts into a timestamped subfolder.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = cfg.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    torch_v = _torch_version()
    report_df = pd.DataFrame(all_rows)
    report_df["run_id"] = run_id
    report_df["torch_version"] = torch_v
    report_df.to_csv(out_dir / "report.csv", index=False)

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_markdown(summary), encoding="utf-8")

    ov = summary["overall"]
    print(f"[done] wrote {out_dir}")
    print(f"[done] scored={ov['N_scored']} skipped={ov['N_skipped']} "
          f"skip_rate={ov['skip_rate']*100:.1f}% MAE={ov.get('MAE')}")
    if summary["skip_threshold_exceeded"]:
        print(f"[warn] skip rate exceeds threshold ({cfg.skip_threshold*100:.0f}%) — baseline not valid.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
