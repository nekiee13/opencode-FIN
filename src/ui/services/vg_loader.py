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


def materialize_for_selected_date(
    *,
    selected_date: str,
    forecast_date: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    from src.followup_ml import vg_store

    use_date = forecast_date or next_business_day(selected_date)
    return vg_store.materialize_vbg_for_date(use_date, db_path=db_path)
