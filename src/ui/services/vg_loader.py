from __future__ import annotations

import csv
import math
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


def _parse_any_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _format_metric_value(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return ""
    return format(float(value), ".4f")


def _ticker_file_symbol(ticker: str) -> str:
    t = str(ticker or "").strip().upper()
    return "GSPC" if t == "SPX" else t


def _load_t0_map(
    *, selected_date: str, raw_tickers_dir: Path, tickers: list[str]
) -> dict[str, float]:
    out: dict[str, float] = {}
    selected = _parse_any_date(selected_date)
    if selected is None:
        return out
    for ticker in tickers:
        symbol = _ticker_file_symbol(ticker)
        csv_path = raw_tickers_dir / f"{symbol}_data.csv"
        if not csv_path.exists():
            continue
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    d = _parse_any_date(str(row.get("Date") or ""))
                    if d != selected:
                        continue
                    raw_close = str(row.get("Close") or "").strip().replace(",", "")
                    try:
                        out[str(ticker).strip().upper()] = float(raw_close)
                    except ValueError:
                        pass
                    break
        except OSError:
            continue
    return out


def _load_weighted_p_map(*, round_dir: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    path = round_dir / "t0_day1_weighted_ensemble.csv"
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = str(row.get("ticker") or "").strip().upper()
                raw = str(row.get("weighted_ensemble") or "").strip().replace(",", "")
                if not ticker:
                    continue
                try:
                    out[ticker] = float(raw)
                except ValueError:
                    continue
    except OSError:
        return {}
    return out


def _load_future_close_map(*, round_dir: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    path = round_dir / "actuals_tplus3.csv"
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = str(row.get("ticker") or "").strip().upper()
                raw = str(row.get("actual_close") or "").strip().replace(",", "")
                if not ticker:
                    continue
                try:
                    out[ticker] = float(raw)
                except ValueError:
                    continue
    except OSError:
        return {}
    return out


def _load_markers_three_day_map(
    *,
    selected_date: str,
    markers_dir: Path | None = None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    selected = _parse_any_date(selected_date)
    if selected is None:
        return out

    use_dir = (markers_dir or (paths.DATA_RAW_DIR / "markers")).resolve()
    csv_path = use_dir / "3_days.csv"
    if not csv_path.exists():
        return out

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                d = _parse_any_date(str(row.get("Date") or ""))
                if d != selected:
                    continue
                for ticker in ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"):
                    raw = str(row.get(ticker) or "").strip().replace(",", "")
                    if not raw:
                        continue
                    try:
                        out[ticker] = float(raw)
                    except ValueError:
                        continue
                break
    except OSError:
        return {}
    return out


def _load_future_close_map_with_fallback(
    *,
    selected_date: str,
    round_dir: Path,
    markers_dir: Path | None = None,
) -> dict[str, float]:
    out = _load_future_close_map(round_dir=round_dir)
    fallback = _load_markers_three_day_map(
        selected_date=selected_date,
        markers_dir=markers_dir,
    )
    if not fallback:
        return out
    for ticker, value in fallback.items():
        if ticker not in out:
            out[ticker] = float(value)
    return out


def build_ann_t0_p_sgn_rows(
    *,
    selected_date: str,
    tickers: list[str],
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
    computed_sgn_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    selected = str(selected_date or "").strip()
    canonical = [str(x).strip().upper() for x in tickers if str(x).strip()]

    if not selected:
        return [
            {
                "Ticker": t,
                "T0": "",
                "P": "",
                "Final Forecast": "",
                "+3-day": "N/A",
                "Computed SGN": "",
                "Realized SGN": "",
                "Magnitude": "",
                "Delta": "N/A",
            }
            for t in canonical
        ]

    use_rounds = (rounds_dir or paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR).resolve()
    use_raw = (raw_tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    round_id = f"anchor-{selected.replace('-', '')}"
    round_dir = use_rounds / round_id

    t0_map = _load_t0_map(
        selected_date=selected, raw_tickers_dir=use_raw, tickers=canonical
    )
    p_map = _load_weighted_p_map(round_dir=round_dir)
    future_map = _load_future_close_map_with_fallback(
        selected_date=selected,
        round_dir=round_dir,
    )

    overrides = {
        str(k or "").strip().upper(): str(v or "").strip()
        for k, v in dict(computed_sgn_overrides or {}).items()
        if str(k or "").strip()
    }

    rows: list[dict[str, str]] = []
    for ticker in canonical:
        t0 = t0_map.get(ticker)
        p = p_map.get(ticker)
        future = future_map.get(ticker)

        trend = 0
        if t0 is not None and p is not None:
            trend = 1 if p > t0 else -1 if p < t0 else 0

        magnitude_value: float | None = None
        if t0 is not None and p is not None:
            magnitude_value = abs(float(t0) - float(p))

        computed_sgn = ""
        if trend != 0:
            candidate = str(overrides.get(ticker) or "").strip()
            if candidate in {"+", "-"}:
                computed_sgn = candidate

        final_forecast: float | None = None
        if (
            t0 is not None
            and magnitude_value is not None
            and trend != 0
            and computed_sgn
        ):
            continuation = 1.0 if computed_sgn == "+" else -1.0
            final_forecast = float(t0) + float(trend) * float(continuation) * float(
                magnitude_value
            )

        realized_sgn = "N/A"
        if t0 is not None and p is not None and future is not None and trend != 0:
            realized = 1 if future > t0 else -1 if future < t0 else 0
            if realized != 0:
                realized_sgn = "+" if realized == trend else "-"

        rows.append(
            {
                "Ticker": ticker,
                "T0": _format_metric_value(t0),
                "P": _format_metric_value(p),
                "Final Forecast": _format_metric_value(final_forecast),
                "+3-day": _format_metric_value(future) if future is not None else "N/A",
                "Computed SGN": computed_sgn,
                "Realized SGN": realized_sgn,
                "Magnitude": _format_metric_value(magnitude_value),
                "Delta": _format_metric_value(
                    abs(float(t0) - float(future))
                    if t0 is not None and future is not None
                    else None
                )
                if t0 is not None and future is not None
                else "N/A",
            }
        )

    return rows


def _sgn_symbol(t0: float | None, value: float | None) -> str:
    if t0 is None or value is None:
        return ""
    if float(value) > float(t0):
        return "+"
    if float(value) < float(t0):
        return "-"
    return "0"


def build_ann_real_vs_computed_rows(
    *,
    selected_date: str,
    tickers: list[str],
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
) -> list[dict[str, str]]:
    selected = str(selected_date or "").strip()
    canonical = [str(x).strip().upper() for x in tickers if str(x).strip()]

    if not selected:
        return [
            {
                "Ticker": t,
                "Real SGN": "",
                "Computed SGN": "",
                "Real Magnitude": "",
                "Computed Magnitude": "",
            }
            for t in canonical
        ]

    use_rounds = (rounds_dir or paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR).resolve()
    use_raw = (raw_tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    round_id = f"anchor-{selected.replace('-', '')}"
    round_dir = use_rounds / round_id

    t0_map = _load_t0_map(
        selected_date=selected,
        raw_tickers_dir=use_raw,
        tickers=canonical,
    )
    p_map = _load_weighted_p_map(round_dir=round_dir)
    future_map = _load_future_close_map_with_fallback(
        selected_date=selected,
        round_dir=round_dir,
    )

    rows: list[dict[str, str]] = []
    for ticker in canonical:
        t0 = t0_map.get(ticker)
        computed = p_map.get(ticker)
        real = future_map.get(ticker)
        real_magnitude = (
            abs(float(real) - float(t0))
            if real is not None and t0 is not None
            else None
        )
        computed_magnitude = (
            abs(float(computed) - float(t0))
            if computed is not None and t0 is not None
            else None
        )

        rows.append(
            {
                "Ticker": ticker,
                "Real SGN": _sgn_symbol(t0, real),
                "Computed SGN": _sgn_symbol(t0, computed),
                "Real Magnitude": _format_metric_value(real_magnitude),
                "Computed Magnitude": _format_metric_value(computed_magnitude),
            }
        )
    return rows


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
    fallback_fh1_dates: set[str] = set()
    for csv_path in sorted(use_fh3.glob("FH3_TABLE_FULL_*.csv"), reverse=True):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                file_hits: set[str] = set()
                for row in reader:
                    asof = str(row.get("AsOf_Cutoff") or "").strip()
                    fh1 = str(row.get("FH_Date1") or "").strip()
                    if _parse_iso_date(fh1) is not None:
                        fallback_fh1_dates.add(fh1)
                    if asof != selected_text:
                        continue
                    if _parse_iso_date(fh1) is not None:
                        file_hits.add(fh1)
                if file_hits:
                    matched_dates.extend(sorted(file_hits))
                    break
        except OSError:
            continue

    if matched_dates:
        return sorted(matched_dates)[0]

    if fallback_fh1_dates:
        next_biz = next_business_day(selected_text)
        if next_biz in fallback_fh1_dates:
            return next_biz
        candidates = sorted(
            x
            for x in fallback_fh1_dates
            if _parse_iso_date(x) is not None and x >= selected_text
        )
        if candidates:
            return candidates[0]

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


def format_violet_blue_rows(
    rows: list[dict[str, Any]],
    *,
    missing_label: str = "model_unavailable",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    label = str(missing_label or "model_unavailable")
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in dict(row).items():
            if str(key) == "Ticker":
                item[str(key)] = value
                continue
            if value is None:
                item[str(key)] = label
                continue
            text = str(value).strip()
            item[str(key)] = label if text == "" else value
        out.append(item)
    return out


def format_blue_table_rows(
    rows: list[dict[str, Any]],
    *,
    missing_label: str = "model_unavailable",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    label = str(missing_label or "model_unavailable")
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in dict(row).items():
            if str(key) == "Ticker":
                item[str(key)] = value
                continue
            if value is None:
                item[str(key)] = label
                continue
            text = str(value).strip()
            if text == "":
                item[str(key)] = label
                continue
            if text == label:
                item[str(key)] = label
                continue
            try:
                item[str(key)] = format(float(text), "05.2f")
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
