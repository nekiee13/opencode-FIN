from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from src.config import paths
from src.ui.services.pipeline_runner import TICKER_ORDER

_MODEL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Torch", "Torch"),
    ("ARIMAX", "ARIMAX"),
    ("PCE", "PCE"),
    ("LSTM", "LSTM"),
    ("GARCH", "GARCH"),
    ("VAR", "VAR"),
    ("RW", "Random-walk"),
    ("ETS", "ETS"),
    ("DYNAMIX", "Dyna"),
)

_TICKER_VALUE_FORMAT: dict[str, str] = {
    "TNX": "0.3f",
    "DJI": "07.1f",
    "SPX": "06.1f",
    "VIX": "05.2f",
    "QQQ": "06.2f",
    "AAPL": "06.2f",
}


@dataclass(frozen=True)
class ModelTableData:
    source_round_id: str | None
    asof_date: str | None
    rows: list[dict[str, Any]]


def _parse_iso(raw: str | None) -> date | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_marker_date(raw: str | None) -> date | None:
    value = str(raw or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _previous_business_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:
        cur -= timedelta(days=1)
    return cur


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_ticker_numeric(ticker: str, value: float | None) -> str | None:
    if value is None:
        return None
    fmt = _TICKER_VALUE_FORMAT.get(str(ticker).upper())
    if not fmt:
        return str(value)
    return format(float(value), fmt)


def _format_model_value(row: dict[str, str], *, ticker: str) -> str | None:
    pred = str(row.get("pred_value", "") or "").strip()
    low = str(row.get("lower_ci", "") or "").strip()
    high = str(row.get("upper_ci", "") or "").strip()
    status = str(row.get("status", "") or "").strip().lower()
    pred_num = _to_float(pred)
    if pred_num is None:
        if status == "model_unavailable":
            return "model_unavailable"
        return None
    pred_fmt = _format_ticker_numeric(ticker, pred_num)
    low_num = _to_float(low)
    high_num = _to_float(high)
    if low_num is not None and high_num is not None:
        low_fmt = _format_ticker_numeric(ticker, low_num)
        high_fmt = _format_ticker_numeric(ticker, high_num)
        return f"{low_fmt}-{high_fmt} ~{pred_fmt}"
    return pred_fmt


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _round_asof_date(rows: list[dict[str, str]]) -> date | None:
    fh1: list[date] = []
    for row in rows:
        if str(row.get("fh_step", "")).strip() != "1":
            continue
        d = _parse_iso(row.get("forecast_date"))
        if d is not None:
            fh1.append(d)
    if not fh1:
        return None
    return _previous_business_day(min(fh1))


def _row_generated_at(rows: list[dict[str, str]]) -> str:
    return max((str(r.get("generated_at", "") or "") for r in rows), default="")


def _choose_round(
    selected_date: str,
    rounds_dir: Path,
) -> tuple[str | None, list[dict[str, str]], date | None]:
    selected = _parse_iso(selected_date)
    candidates: list[tuple[date | None, str, list[dict[str, str]], str]] = []

    for csv_path in sorted(rounds_dir.glob("*/t0_forecasts.csv")):
        rows = _read_rows(csv_path)
        if not rows:
            continue
        round_id = str(
            rows[0].get("round_id", csv_path.parent.name) or csv_path.parent.name
        )
        asof = _round_asof_date(rows)
        generated = _row_generated_at(rows)
        candidates.append((asof, round_id, rows, generated))

    if not candidates:
        return None, [], None

    if selected is not None:
        exact = [x for x in candidates if x[0] == selected]
        if exact:
            exact.sort(key=lambda x: x[3])
            asof, round_id, rows, _ = exact[-1]
            return round_id, rows, asof

        prior = [x for x in candidates if x[0] is not None and x[0] <= selected]
        if prior:
            prior.sort(key=lambda x: x[0] if x[0] is not None else date.min)
            asof, round_id, rows, _ = prior[-1]
            return round_id, rows, asof

        return None, [], None

    candidates.sort(key=lambda x: x[0] if x[0] is not None else date.min)
    asof, round_id, rows, _ = candidates[-1]
    return round_id, rows, asof


def load_model_table(
    selected_date: str,
    rounds_dir: Path | None = None,
) -> ModelTableData:
    use_rounds = rounds_dir or paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR
    round_id, rows, asof = _choose_round(selected_date, use_rounds)
    if not rows:
        return ModelTableData(source_round_id=None, asof_date=None, rows=[])

    best: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        ticker = str(row.get("ticker", "") or "").strip().upper()
        model = str(row.get("model", "") or "").strip()
        if not ticker or not model:
            continue
        try:
            step = int(str(row.get("fh_step", "") or "0"))
        except ValueError:
            step = 0
        key = (ticker, model)
        prev = best.get(key)
        prev_step = int(str(prev.get("fh_step", "0")) if prev else "0")
        if prev is None or step >= prev_step:
            best[key] = row

    out_rows: list[dict[str, Any]] = []
    for ticker in TICKER_ORDER:
        out: dict[str, Any] = {"Ticker": ticker}
        has_any = False
        for source_name, display_name in _MODEL_COLUMNS:
            value = _format_model_value(
                best.get((ticker, source_name), {}), ticker=ticker
            )
            out[display_name] = value
            has_any = has_any or (value is not None)
        if has_any:
            out_rows.append(out)

    return ModelTableData(
        source_round_id=round_id,
        asof_date=asof.isoformat() if asof else None,
        rows=out_rows,
    )


def load_marker_values(
    selected_date: str,
    markers_dir: Path | None = None,
) -> dict[str, dict[str, float | None]]:
    date_key = _parse_iso(selected_date)
    use_dir = markers_dir or (paths.DATA_RAW_DIR / "markers")
    out: dict[str, dict[str, float | None]] = {}
    marker_files = {
        "oraclum": use_dir / "oraclum.csv",
        "rd": use_dir / "rd.csv",
        "85220": use_dir / "85220.csv",
    }

    for marker_name, marker_file in marker_files.items():
        values = cast(
            dict[str, float | None],
            {ticker: None for ticker in TICKER_ORDER},
        )
        if not marker_file.exists() or date_key is None:
            out[marker_name] = values
            continue
        with marker_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            selected_row: dict[str, str] | None = None
            latest_prior_row: tuple[date, dict[str, str]] | None = None
            for row in reader:
                parsed = _parse_marker_date(row.get("Date"))
                if parsed is None:
                    continue
                row_copy = dict(row)
                if parsed == date_key:
                    selected_row = row_copy
                    break
                if parsed <= date_key and (
                    latest_prior_row is None or parsed > latest_prior_row[0]
                ):
                    latest_prior_row = (parsed, row_copy)
            if selected_row is None and latest_prior_row is not None:
                selected_row = latest_prior_row[1]
            if selected_row is None:
                continue
            for ticker in TICKER_ORDER:
                raw = str(selected_row.get(ticker, "") or "").strip()
                if raw:
                    try:
                        values[ticker] = float(raw.replace(",", ""))
                    except ValueError:
                        values[ticker] = None
        out[marker_name] = values

    return out


def _extract_numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "~" in text:
        text = text.split("~")[-1].strip()
    text = text.split(" ")[0]
    try:
        return float(text)
    except ValueError:
        return None


def build_marker_comparison_rows(
    *,
    model_rows: list[dict[str, Any]],
    marker_values: dict[str, dict[str, float | None]],
) -> list[dict[str, Any]]:
    by_ticker = {str(row.get("Ticker", "")): row for row in model_rows}
    out: list[dict[str, Any]] = []
    for ticker in TICKER_ORDER:
        model_row = by_ticker.get(ticker, {})
        ml_value = _extract_numeric(model_row.get("Torch"))
        oraclum = marker_values.get("oraclum", {}).get(ticker)
        rd_value = marker_values.get("rd", {}).get(ticker)
        v85220 = marker_values.get("85220", {}).get(ticker)

        def pct_delta(ref: float | None) -> float | None:
            if ref in (None, 0) or ml_value is None:
                return None
            return ((ml_value - float(ref)) / float(ref)) * 100.0

        out.append(
            {
                "Ticker": ticker,
                "ML": _format_ticker_numeric(ticker, ml_value),
                "Oraclum": _format_ticker_numeric(ticker, oraclum),
                "RD": _format_ticker_numeric(ticker, rd_value),
                "85220": _format_ticker_numeric(ticker, v85220),
                "Delta_Oraclum_%": pct_delta(oraclum),
                "Delta_RD_%": pct_delta(rd_value),
                "Delta_85220_%": pct_delta(v85220),
            }
        )
    return out
