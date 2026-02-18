# ------------------------
# scripts\workers\pce_worker.py
# ------------------------
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _require_path(v: Optional[str], name: str) -> str:
    if v is None or str(v).strip() == "":
        raise ValueError(f"Missing required field: {name}")
    return str(v)


@dataclass(frozen=True)
class WorkerInput:
    enriched_data_csv: str
    exog_train_csv: Optional[str]
    exog_future_csv: Optional[str]
    ticker: str
    target_col: Optional[str]
    fh: Optional[int]
    forecast_csv_out: str


def _parse_input(inp: Dict[str, Any]) -> WorkerInput:
    enriched_csv = _require_path(inp.get("enriched_data_csv"), "enriched_data_csv")
    forecast_out = _require_path(inp.get("forecast_csv_out"), "forecast_csv_out")

    ticker = str(inp.get("ticker") or "").strip()

    target_col = inp.get("target_col")
    target_col = str(target_col).strip() if target_col is not None and str(target_col).strip() else None

    fh = inp.get("fh")
    fh_i: Optional[int] = None
    if fh is not None and str(fh).strip() != "":
        try:
            fh_i = int(fh)
        except Exception:
            fh_i = None

    exog_train = inp.get("exog_train_csv")
    exog_train = str(exog_train).strip() if exog_train is not None and str(exog_train).strip() else None

    exog_future = inp.get("exog_future_csv")
    exog_future = str(exog_future).strip() if exog_future is not None and str(exog_future).strip() else None

    return WorkerInput(
        enriched_data_csv=enriched_csv,
        exog_train_csv=exog_train,
        exog_future_csv=exog_future,
        ticker=ticker,
        target_col=target_col,
        fh=fh_i,
        forecast_csv_out=forecast_out,
    )


def _coerce_datetime_index(df, date_col_candidates=("Date", "date", "Datetime", "datetime")):
    """
    Strategy:
    1) If a known date column exists -> parse and set as index.
    2) Else try first column if it parses as mostly dates.
    3) Else leave as-is (canonical predict will fail fast if index invalid).
    """
    import pandas as pd

    cols = list(df.columns)
    for c in date_col_candidates:
        if c in cols:
            df[c] = pd.to_datetime(df[c], errors="coerce")
            df = df.dropna(subset=[c]).set_index(c)
            df.index = pd.to_datetime(df.index, errors="coerce")
            return df.sort_index()

    if len(cols) > 0:
        c0 = cols[0]
        dt0 = pd.to_datetime(df[c0], errors="coerce")
        if dt0.notna().sum() >= max(3, int(0.5 * len(dt0))):
            df[c0] = dt0
            df = df.dropna(subset=[c0]).set_index(c0)
            df.index = pd.to_datetime(df.index, errors="coerce")
            return df.sort_index()

    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="FIN PCE-NARX worker (NumPy 2.x environment)")
    ap.add_argument("--in", dest="in_path", required=True, help="Input JSON path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output JSON path")
    args = ap.parse_args()

    out: Dict[str, Any] = {
        "status": "ERROR",
        "model": "PCE_NARX",
        "time_utc": _utc_iso(),
        "ticker": "",
        "forecast_csv": None,
        "error": None,
        "traceback": None,
        "meta": {},
    }

    try:
        payload = _read_json(args.in_path)
        wi = _parse_input(payload)
        out["ticker"] = wi.ticker

        import pandas as pd

        # Read enriched data
        enriched_df = pd.read_csv(wi.enriched_data_csv)
        enriched_df = _coerce_datetime_index(enriched_df)
        enriched_df.index = pd.to_datetime(enriched_df.index, errors="coerce")
        enriched_df = enriched_df.dropna(axis=0, how="all").sort_index()

        # Read exogenous (optional)
        ex_train_df = None
        if wi.exog_train_csv:
            ex_train_df = pd.read_csv(wi.exog_train_csv)
            ex_train_df = _coerce_datetime_index(ex_train_df)
            ex_train_df.index = pd.to_datetime(ex_train_df.index, errors="coerce")
            ex_train_df = ex_train_df.dropna(axis=0, how="all").sort_index()

        ex_future_df = None
        if wi.exog_future_csv:
            ex_future_df = pd.read_csv(wi.exog_future_csv)
            ex_future_df = _coerce_datetime_index(ex_future_df)
            ex_future_df.index = pd.to_datetime(ex_future_df.index, errors="coerce")
            ex_future_df = ex_future_df.dropna(axis=0, how="all").sort_index()

        # Canonical compute (inside PCE venv)
        from src.models.pce_narx import predict_pce_narx

        pred_df = predict_pce_narx(
            enriched_data=enriched_df,
            ticker=wi.ticker,
            target_col=wi.target_col,
            fh=wi.fh,
            exog_train_df=ex_train_df,
            exog_future_df=ex_future_df,
            progress_callback=None,
        )

        if pred_df is None or getattr(pred_df, "empty", True):
            out["status"] = "INSUFFICIENT_DATA"
            out["error"] = "predict_pce_narx returned None/empty"
            _write_json(args.out_path, out)
            return 3

        # Write forecast CSV (portable artifact)
        forecast_out = os.path.abspath(wi.forecast_csv_out)
        os.makedirs(os.path.dirname(forecast_out) or ".", exist_ok=True)

        df_to_write = pred_df.copy()
        df_to_write.index.name = "Date"
        df_to_write.reset_index().to_csv(forecast_out, index=False)

        out["status"] = "OK"
        out["forecast_csv"] = forecast_out
        out["meta"] = {
            "rows": int(len(pred_df)),
            "cols": list(getattr(pred_df, "columns", [])),
        }
        _write_json(args.out_path, out)
        return 0

    except Exception as e:
        out["status"] = "ERROR"
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
        _write_json(args.out_path, out)
        return 2


if __name__ == "__main__":
    sys.exit(main())
