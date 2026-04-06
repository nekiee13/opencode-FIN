from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import paths


def next_business_day(iso_date: str) -> str:
    cur = datetime.strptime(iso_date, "%Y-%m-%d").date()
    cur += timedelta(days=1)
    while cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur.isoformat()


def _parse_iso_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_target_forecast_date(
    *,
    selected_date: str,
    fh3_dir: Path | None = None,
) -> str:
    selected_text = str(selected_date or "").strip()
    if not selected_text:
        return ""

    selected = _parse_iso_date(selected_text)
    if selected is None:
        return selected_text

    use_fh3 = (fh3_dir or paths.OUT_I_CALC_FH3_DIR).resolve()
    if not use_fh3.exists():
        return selected_text

    matched_dates: list[str] = []
    for csv_path in sorted(use_fh3.glob("FH3_TABLE_FULL_*.csv"), reverse=True):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                file_hits: set[str] = set()
                for row in reader:
                    asof = str(row.get("AsOf_Cutoff") or "").strip()
                    if asof != selected_text:
                        continue
                    fh1 = str(row.get("FH_Date1") or "").strip()
                    if _parse_iso_date(fh1) is not None:
                        file_hits.add(fh1)
                if file_hits:
                    matched_dates.extend(sorted(file_hits))
                    break
        except OSError:
            continue

    if matched_dates:
        return sorted(matched_dates)[0]
    return selected_text


def pick_anchored_violet_date(
    *,
    selected_date: str,
    available_dates: list[str],
    fh3_dir: Path | None = None,
) -> str | None:
    valid = {
        str(x).strip()
        for x in available_dates
        if _parse_iso_date(str(x).strip()) is not None
    }
    if not valid:
        return None

    selected_text = str(selected_date or "").strip()
    if selected_text in valid:
        return selected_text

    target_text = resolve_target_forecast_date(
        selected_date=selected_text,
        fh3_dir=fh3_dir,
    )
    if str(target_text) in valid:
        return str(target_text)
    return None


def list_violet_forecast_dates(db_path: Path | None = None) -> list[str]:
    use_path = (db_path or paths.OUT_I_CALC_ML_VG_DB_PATH).resolve()
    if not use_path.exists():
        return []

    conn = sqlite3.connect(str(use_path))
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT forecast_date
            FROM violet_scores
            WHERE forecast_date IS NOT NULL AND forecast_date <> ''
            ORDER BY forecast_date DESC
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    return [str(row[0]) for row in rows if row and row[0]]


def suggest_forecast_date(
    *,
    selected_date: str,
    available_dates: list[str],
) -> str | None:
    if not available_dates:
        return None

    normalized = sorted(
        {x for x in available_dates if _parse_iso_date(x) is not None},
        reverse=True,
    )
    if not normalized:
        return None

    selected = _parse_iso_date(selected_date)
    if selected is None:
        return normalized[0]

    selected_text = selected.isoformat()
    if selected_text in normalized:
        return selected_text

    next_biz_text = next_business_day(selected_text)
    if next_biz_text in normalized:
        return next_biz_text

    parsed = [(_parse_iso_date(x), x) for x in normalized]
    prior = [x for d, x in parsed if d is not None and d <= selected]
    if prior:
        return prior[0]
    return normalized[0]


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


def format_green_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in dict(row).items():
            if str(key) == "Ticker":
                item[str(key)] = value
                continue
            text = str(value).strip() if value is not None else ""
            if not text:
                item[str(key)] = None
                continue
            try:
                item[str(key)] = format(float(text), "06.3f")
            except ValueError:
                item[str(key)] = value
        out.append(item)
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
    fh3_dir: Path | None = None,
) -> dict[str, Any]:
    from src.followup_ml import vg_store

    use_date = forecast_date or resolve_target_forecast_date(
        selected_date=selected_date,
        fh3_dir=fh3_dir,
    )
    return vg_store.materialize_vbg_for_date(
        use_date,
        db_path=db_path,
        policy_name=policy_name,
        memory_tail=memory_tail,
        bootstrap_enabled=bootstrap_enabled,
        bootstrap_score=bootstrap_score,
    )
