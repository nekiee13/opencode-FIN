from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from src.models import compat_api as models_api
from src.ui.services.pipeline_runner import TICKER_ORDER
from src.utils.calc_snapshots import persist_pp_snapshot, persist_ti_snapshot
from src.utils.pivots import calculate_latest_pivot_points

RUNTIME_TICKER_MAP: dict[str, str] = {"SPX": "GSPC"}


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_logical_ticker(ticker: str) -> str:
    text = str(ticker or "").strip().upper().replace("^", "")
    if text == "GSPC":
        return "SPX"
    return text


def runtime_ticker_for(logical_ticker: str) -> str:
    logical = normalize_logical_ticker(logical_ticker)
    return str(RUNTIME_TICKER_MAP.get(logical, logical))


def normalize_ticker_list(tickers: Sequence[str] | None) -> list[str]:
    if tickers is None:
        return [str(x) for x in TICKER_ORDER]
    out: list[str] = []
    for raw in tickers:
        logical = normalize_logical_ticker(str(raw))
        if not logical:
            continue
        if logical not in out:
            out.append(logical)
    return out


def _ticker_backfill_one(*, selected_date: str, logical_ticker: str) -> dict[str, Any]:
    runtime_ticker = runtime_ticker_for(logical_ticker)
    run_out: dict[str, Any] = {
        "ticker": str(logical_ticker),
        "runtime_ticker": str(runtime_ticker),
        "selected_date": str(selected_date),
        "status": "error",
        "as_of_date": "",
        "ti_path": "",
        "pp_path": "",
        "error": "",
    }

    enriched = models_api.run_external_ti_calculator(
        runtime_ticker,
        history_mode="replay",
        as_of_date=str(selected_date),
    )
    if enriched is None or enriched.empty:
        run_out["error"] = "ti_worker_empty"
        return run_out

    latest_indicators = cast_series(enriched.iloc[-1])
    pivot_payload = calculate_latest_pivot_points(enriched)
    if pivot_payload is None:
        run_out["error"] = "pivot_calc_failed"
        return run_out

    as_of_ts = pd.Timestamp(latest_indicators.name)
    ti_path = persist_ti_snapshot(
        ticker=str(logical_ticker),
        asof_date=as_of_ts,
        latest_indicators=latest_indicators,
        pivot_data=pivot_payload,
    )
    pp_path = persist_pp_snapshot(
        ticker=str(logical_ticker),
        asof_date=as_of_ts,
        pivot_data=pivot_payload,
    )

    run_out.update(
        {
            "status": "success",
            "as_of_date": as_of_ts.strftime("%Y-%m-%d"),
            "ti_path": str(Path(ti_path).resolve()),
            "pp_path": str(Path(pp_path).resolve()),
            "error": "",
        }
    )
    return run_out


def cast_series(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(value)


def backfill_ti_pp_for_date(
    *,
    selected_date: str,
    tickers: Sequence[str] | None = None,
    stop_on_error: bool = True,
) -> dict[str, Any]:
    date_text = str(selected_date or "").strip()
    if not date_text:
        return {
            "status": "error",
            "index_code": "TI_PP_DATE_REQUIRED",
            "selected_date": "",
            "tickers": [],
            "results": [],
            "generated_at": _utc_now_iso(),
        }

    ticker_list = normalize_ticker_list(tickers)
    if not ticker_list:
        return {
            "status": "error",
            "index_code": "TI_PP_TICKERS_REQUIRED",
            "selected_date": date_text,
            "tickers": [],
            "results": [],
            "generated_at": _utc_now_iso(),
        }

    results: list[dict[str, Any]] = []
    for ticker in ticker_list:
        item = _ticker_backfill_one(selected_date=date_text, logical_ticker=ticker)
        results.append(item)
        if stop_on_error and str(item.get("status") or "") != "success":
            break

    success_count = sum(
        1 for row in results if str(row.get("status") or "") == "success"
    )
    failed_count = len(results) - success_count
    status = (
        "success" if failed_count == 0 and len(results) == len(ticker_list) else "error"
    )
    index_code = "TI_PP_OK" if status == "success" else "TI_PP_FAILED"
    return {
        "status": status,
        "index_code": index_code,
        "selected_date": date_text,
        "tickers": ticker_list,
        "results": results,
        "success_count": int(success_count),
        "failed_count": int(failed_count),
        "generated_at": _utc_now_iso(),
    }


__all__ = [
    "RUNTIME_TICKER_MAP",
    "normalize_logical_ticker",
    "runtime_ticker_for",
    "normalize_ticker_list",
    "backfill_ti_pp_for_date",
]
