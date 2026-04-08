from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ANN_EXCLUDED_MARKERS: set[str] = {"RD", "85220", "MICHO"}

TI_FEATURE_NAMES: tuple[str, ...] = (
    "50-day MA",
    "200-day MA",
    "RSI (14)",
    "Stochastic %K",
    "ATR (14)",
    "ADX (14)",
    "CCI (14)",
    "Williams %R",
    "Ultimate Oscillator",
    "ROC (10)",
    "BullBear Power",
)

PP_FEATURE_NAMES: tuple[str, ...] = (
    "S3(Classic)",
    "S2(Classic)",
    "S1(Classic)",
    "Pivot Points(Classic)",
    "R1(Classic)",
    "R2(Classic)",
    "R3(Classic)",
    "S3(Fibonacci)",
    "S2(Fibonacci)",
    "S1(Fibonacci)",
    "Pivot Points(Fibonacci)",
    "R1(Fibonacci)",
    "R2(Fibonacci)",
    "R3(Fibonacci)",
    "S3(Camarilla)",
    "S2(Camarilla)",
    "S1(Camarilla)",
    "Pivot Points(Camarilla)",
    "R1(Camarilla)",
    "R2(Camarilla)",
    "R3(Camarilla)",
    "S3(Woodie's)",
    "S2(Woodie's)",
    "S1(Woodie's)",
    "Pivot Points(Woodie's)",
    "R1(Woodie's)",
    "R2(Woodie's)",
    "R3(Woodie's)",
    "S3(DeMark's)",
    "S2(DeMark's)",
    "S1(DeMark's)",
    "Pivot Points(DeMark's)",
    "R1(DeMark's)",
    "R2(DeMark's)",
    "R3(DeMark's)",
)

SVL_HURST_FEATURE_NAMES: tuple[str, ...] = ("H20", "H60", "H120")

TDA_H1_FEATURE_NAMES: tuple[str, ...] = (
    "H1_MaxPersistence",
    "H1_CountAbove_Thr",
    "H1_Entropy",
)


def _normalize_ticker(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if text == "GSPC":
        return "SPX"
    return text


def _parse_float(raw: str) -> float | None:
    text = str(raw or "").strip()
    if not text or text in {"-", "NA", "N/A", "nan", "NaN"}:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _record(
    *,
    as_of_date: str,
    ticker: str,
    feature_name: str,
    feature_value: float | None,
    source_family: str,
    source_file: Path,
) -> dict[str, Any]:
    return {
        "as_of_date": str(as_of_date),
        "ticker": str(ticker),
        "feature_name": str(feature_name),
        "feature_value": feature_value,
        "source_family": str(source_family),
        "source_file": str(source_file),
        "value_status": "present" if feature_value is not None else "missing",
    }


def _dedupe(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in records:
        key = (
            str(item.get("source_family") or ""),
            str(item.get("as_of_date") or ""),
            str(item.get("ticker") or ""),
            str(item.get("feature_name") or ""),
        )
        by_key[key] = item
    return list(by_key.values())


def _collect_ti_records(ti_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not ti_dir.exists():
        return out
    for file_path in sorted(ti_dir.glob("*.csv")):
        ticker = _normalize_ticker(file_path.stem)
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                as_of_date = str(row.get("Date") or "").strip()
                if not as_of_date:
                    continue
                for feature_name in TI_FEATURE_NAMES:
                    if feature_name not in row:
                        continue
                    out.append(
                        _record(
                            as_of_date=as_of_date,
                            ticker=ticker,
                            feature_name=feature_name,
                            feature_value=_parse_float(
                                str(row.get(feature_name) or "")
                            ),
                            source_family="ti",
                            source_file=file_path,
                        )
                    )
    return out


def _collect_pp_records(pp_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not pp_dir.exists():
        return out
    for file_path in sorted(pp_dir.glob("*.csv")):
        ticker = _normalize_ticker(file_path.stem)
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                as_of_date = str(row.get("Date") or "").strip()
                if not as_of_date:
                    continue
                for feature_name in PP_FEATURE_NAMES:
                    if feature_name not in row:
                        continue
                    out.append(
                        _record(
                            as_of_date=as_of_date,
                            ticker=ticker,
                            feature_name=feature_name,
                            feature_value=_parse_float(
                                str(row.get(feature_name) or "")
                            ),
                            source_family="pivot",
                            source_file=file_path,
                        )
                    )
    return out


def _collect_svl_records(svl_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not svl_dir.exists():
        return out
    for file_path in sorted(svl_dir.glob("SVL_METRICS_*.csv")):
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = _normalize_ticker(str(row.get("Ticker") or ""))
                as_of_date = str(row.get("Ticker_AsOf") or "").strip()
                if not ticker or not as_of_date:
                    continue
                for feature_name in SVL_HURST_FEATURE_NAMES:
                    if feature_name not in row:
                        continue
                    out.append(
                        _record(
                            as_of_date=as_of_date,
                            ticker=ticker,
                            feature_name=feature_name,
                            feature_value=_parse_float(
                                str(row.get(feature_name) or "")
                            ),
                            source_family="hurst",
                            source_file=file_path,
                        )
                    )
    return out


def _collect_tda_h1_records(tda_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not tda_dir.exists():
        return out
    for file_path in sorted(tda_dir.glob("TDA_METRICS_*.csv")):
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = _normalize_ticker(str(row.get("Ticker") or ""))
                as_of_date = str(row.get("Ticker_AsOf") or "").strip()
                if not ticker or not as_of_date:
                    continue
                for feature_name in TDA_H1_FEATURE_NAMES:
                    if feature_name not in row:
                        continue
                    out.append(
                        _record(
                            as_of_date=as_of_date,
                            ticker=ticker,
                            feature_name=feature_name,
                            feature_value=_parse_float(
                                str(row.get(feature_name) or "")
                            ),
                            source_family="tda_h1",
                            source_file=file_path,
                        )
                    )
    return out


def collect_ann_feature_records(
    *,
    ti_dir: Path,
    pp_dir: Path,
    svl_dir: Path,
    tda_dir: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    records.extend(_collect_ti_records(ti_dir.resolve()))
    records.extend(_collect_pp_records(pp_dir.resolve()))
    records.extend(_collect_svl_records(svl_dir.resolve()))
    records.extend(_collect_tda_h1_records(tda_dir.resolve()))
    return _dedupe(records)


__all__ = [
    "ANN_EXCLUDED_MARKERS",
    "TI_FEATURE_NAMES",
    "PP_FEATURE_NAMES",
    "SVL_HURST_FEATURE_NAMES",
    "TDA_H1_FEATURE_NAMES",
    "collect_ann_feature_records",
]
