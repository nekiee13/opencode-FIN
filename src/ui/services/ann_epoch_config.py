from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence

from src.config import paths

TICKER_ORDER: tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
CSV_COLUMNS: tuple[str, ...] = ("Ticker", "SGN", "Magnitude")

DEFAULT_EPOCHS: dict[str, dict[str, int]] = {
    "TNX": {"SGN": 200, "Magnitude": 600},
    "DJI": {"SGN": 200, "Magnitude": 1200},
    "SPX": {"SGN": 200, "Magnitude": 900},
    "VIX": {"SGN": 200, "Magnitude": 2200},
    "QQQ": {"SGN": 200, "Magnitude": 1200},
    "AAPL": {"SGN": 200, "Magnitude": 600},
}


def epoch_csv_path(path: Path | None = None) -> Path:
    return (path or (paths.OUT_I_CALC_DIR / "ANN" / "epoch.csv")).resolve()


def _default_rows() -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for ticker in TICKER_ORDER:
        payload = DEFAULT_EPOCHS.get(ticker) or {"SGN": 200, "Magnitude": 600}
        rows.append(
            {
                "Ticker": ticker,
                "SGN": int(payload.get("SGN") or 200),
                "Magnitude": int(payload.get("Magnitude") or 600),
            }
        )
    return rows


def _coerce_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(float(text))
    except ValueError:
        return None
    return int(parsed)


def validate_epoch_rows(
    rows: Sequence[dict[str, Any]],
    *,
    min_epochs: int = 1,
    max_epochs: int = 10000,
) -> tuple[list[dict[str, int | str]], list[str]]:
    errors: list[str] = []
    normalized: dict[str, dict[str, int | str]] = {}
    for row in list(rows):
        ticker = str((row or {}).get("Ticker") or "").strip().upper()
        if ticker not in TICKER_ORDER:
            errors.append(f"Unsupported ticker in epoch config: {ticker or 'EMPTY'}")
            continue
        sgn = _coerce_int((row or {}).get("SGN"))
        mag = _coerce_int((row or {}).get("Magnitude"))
        if sgn is None:
            errors.append(f"Invalid SGN epoch for {ticker}")
            continue
        if mag is None:
            errors.append(f"Invalid Magnitude epoch for {ticker}")
            continue
        if not (int(min_epochs) <= sgn <= int(max_epochs)):
            errors.append(f"SGN epoch out of range for {ticker}: {sgn}")
            continue
        if not (int(min_epochs) <= mag <= int(max_epochs)):
            errors.append(f"Magnitude epoch out of range for {ticker}: {mag}")
            continue
        normalized[ticker] = {"Ticker": ticker, "SGN": int(sgn), "Magnitude": int(mag)}

    for ticker in TICKER_ORDER:
        if ticker not in normalized:
            errors.append(f"Missing epoch row for {ticker}")

    ordered = [normalized[t] for t in TICKER_ORDER if t in normalized]
    return ordered, errors


def save_epoch_rows(
    rows: Sequence[dict[str, Any]],
    *,
    path: Path | None = None,
) -> tuple[list[dict[str, int | str]], list[str], Path]:
    out_path = epoch_csv_path(path)
    normalized, errors = validate_epoch_rows(rows)
    if errors:
        return [], errors, out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in normalized:
            writer.writerow(
                {
                    "Ticker": str(row.get("Ticker") or ""),
                    "SGN": int(row.get("SGN") or 0),
                    "Magnitude": int(row.get("Magnitude") or 0),
                }
            )
    return normalized, [], out_path


def load_epoch_rows(
    *, path: Path | None = None
) -> tuple[list[dict[str, int | str]], list[str], Path]:
    out_path = epoch_csv_path(path)
    if not out_path.exists():
        seeded = _default_rows()
        saved, errors, _ = save_epoch_rows(seeded, path=out_path)
        return (saved if not errors else seeded), errors, out_path

    rows: list[dict[str, Any]] = []
    try:
        with out_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    {
                        "Ticker": str((row or {}).get("Ticker") or ""),
                        "SGN": (row or {}).get("SGN"),
                        "Magnitude": (row or {}).get("Magnitude"),
                    }
                )
    except OSError:
        rows = []

    normalized, errors = validate_epoch_rows(rows)
    if errors:
        seeded = _default_rows()
        saved, save_errors, _ = save_epoch_rows(seeded, path=out_path)
        merged = list(errors) + list(save_errors)
        return (saved if not save_errors else seeded), merged, out_path
    return normalized, [], out_path


def epochs_for_ticker_mode(
    rows: Sequence[dict[str, Any]],
    *,
    ticker: str,
    mode: str,
    fallback: int,
) -> int:
    ticker_u = str(ticker or "").strip().upper()
    mode_key = "SGN" if str(mode or "").strip().lower() == "sgn" else "Magnitude"
    for row in list(rows):
        if str((row or {}).get("Ticker") or "").strip().upper() != ticker_u:
            continue
        parsed = _coerce_int((row or {}).get(mode_key))
        if parsed is not None:
            return int(parsed)
    return int(fallback)


__all__ = [
    "CSV_COLUMNS",
    "DEFAULT_EPOCHS",
    "TICKER_ORDER",
    "epoch_csv_path",
    "epochs_for_ticker_mode",
    "load_epoch_rows",
    "save_epoch_rows",
    "validate_epoch_rows",
]
