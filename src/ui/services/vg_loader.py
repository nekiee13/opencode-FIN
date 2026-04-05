from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def next_business_day(iso_date: str) -> str:
    cur = datetime.strptime(iso_date, "%Y-%m-%d").date()
    cur += timedelta(days=1)
    while cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur.isoformat()


def matrix_to_rows(
    *,
    matrix: dict[str, dict[str, Any]],
    models: list[str],
    tickers: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ticker in tickers:
        row: dict[str, Any] = {"Ticker": ticker}
        for model in models:
            row[model] = matrix.get(model, {}).get(ticker)
        out.append(row)
    return out


def green_meta_to_rows(
    *,
    green_meta: dict[str, dict[str, dict[str, int]]],
    models: list[str],
    tickers: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        for model in models:
            meta = green_meta.get(model, {}).get(ticker, {})
            rows.append(
                {
                    "Ticker": ticker,
                    "Model": model,
                    "Real Rounds Used": int(meta.get("real_rounds_used", 0) or 0),
                    "Dummy Slots Used": int(meta.get("bootstrap_slots_used", 0) or 0),
                }
            )
    return rows


def materialize_for_selected_date(
    *,
    selected_date: str,
    forecast_date: str | None = None,
    db_path: Path | None = None,
    memory_tail: int | None = None,
    bootstrap_enabled: bool | None = None,
    bootstrap_score: float | None = None,
    policy_name: str | None = None,
) -> dict[str, Any]:
    from src.followup_ml import vg_store

    use_date = forecast_date or next_business_day(selected_date)
    return vg_store.materialize_vbg_for_date(
        use_date,
        db_path=db_path,
        policy_name=policy_name,
        memory_tail=memory_tail,
        bootstrap_enabled=bootstrap_enabled,
        bootstrap_score=bootstrap_score,
    )
