from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd

from src.config import paths


TI_COLUMNS: List[str] = [
    "Date",
    "Current Value",
    "Classic Pivot Point",
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
]

PP_METHODS: Tuple[str, ...] = (
    "Classic",
    "Fibonacci",
    "Camarilla",
    "Woodie's",
    "DeMark's",
)

PP_LEVELS: Tuple[str, ...] = ("S3", "S2", "S1", "Pivot Points", "R1", "R2", "R3")

ML_TICKER_COL = "Ticker"
ML_MAIN_COLUMNS: List[str] = [
    "Ticker",
    "Torch",
    "ARIMAX",
    "PCE",
    "LSTM",
    "GARCH",
    "VAR",
    "RW",
    "ETS",
    "DynaMix",
]

ML_META_COLUMNS: List[str] = [
    *ML_MAIN_COLUMNS,
    "ARIMAX_Lower",
    "ARIMAX_Upper",
    "PCE_Lower",
    "PCE_Upper",
    "LSTM_Lower",
    "LSTM_Upper",
    "DynaMix_Secondary",
]


def _safe_date_text(value: Any) -> str:
    dt = pd.Timestamp(value)
    return str(dt.strftime("%Y-%m-%d"))


def _safe_float(value: Any) -> float:
    try:
        f = float(value)
        if np.isfinite(f):
            return f
    except Exception:
        pass
    return float("nan")


def _sanitize_ticker_for_filename(ticker: str) -> str:
    return str(ticker).replace("^", "").strip()


def _pivot_to_mapping(pivot_data: Any) -> Dict[str, Dict[str, Any]]:
    if pivot_data is None:
        return {}
    if isinstance(pivot_data, dict):
        return cast(Dict[str, Dict[str, Any]], pivot_data)
    payload = getattr(pivot_data, "pivot_data", None)
    if isinstance(payload, dict):
        return cast(Dict[str, Dict[str, Any]], payload)
    return {}


def _sort_by_date(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" not in df.columns or df.empty:
        return df
    out = cast(pd.DataFrame, df.copy())
    out["_date_sort"] = pd.to_datetime(out["Date"], errors="coerce")
    out = cast(pd.DataFrame, out.sort_values(by=["_date_sort", "Date"], kind="stable"))
    out = cast(pd.DataFrame, out.drop(columns=["_date_sort"]))
    return cast(pd.DataFrame, out.reset_index(drop=True))


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return cast(pd.DataFrame, pd.read_csv(path))


def _upsert_by_key(
    df: pd.DataFrame, row: Mapping[str, Any], key_col: str
) -> pd.DataFrame:
    incoming_key = str(row.get(key_col, "")).strip()
    row_df = pd.DataFrame([dict(row)])
    if df is None or df.empty:
        return row_df

    out = cast(pd.DataFrame, df.copy())
    if key_col in out.columns:
        out[key_col] = out[key_col].astype(str).str.strip()
        out = cast(pd.DataFrame, out.loc[out[key_col] != incoming_key, :].copy())
    return cast(pd.DataFrame, pd.concat([out, row_df], ignore_index=True))


def _sort_by_ticker_order(
    df: pd.DataFrame, ticker_order: Sequence[str]
) -> pd.DataFrame:
    if df.empty or ML_TICKER_COL not in df.columns:
        return df

    order_map = {str(t).strip(): i for i, t in enumerate(ticker_order)}
    out = cast(pd.DataFrame, df.copy())
    out[ML_TICKER_COL] = out[ML_TICKER_COL].astype(str).str.strip()
    out["_ord"] = out[ML_TICKER_COL].map(order_map)
    out["_ord"] = pd.to_numeric(out["_ord"], errors="coerce").fillna(10_000)
    out = cast(pd.DataFrame, out.sort_values(by=["_ord", ML_TICKER_COL], kind="stable"))
    out = cast(pd.DataFrame, out.drop(columns=["_ord"]))
    return cast(pd.DataFrame, out.reset_index(drop=True))


def _ti_row_from_snapshot(
    *,
    asof_date: Any,
    latest_indicators: Mapping[str, Any],
    pivot_data: Any,
) -> Dict[str, Any]:
    pivots = _pivot_to_mapping(pivot_data)
    classic = pivots.get("Classic", {}) if isinstance(pivots, dict) else {}

    row: Dict[str, Any] = {
        "Date": _safe_date_text(asof_date),
        "Current Value": _safe_float(latest_indicators.get("Close")),
        "Classic Pivot Point": _safe_float(classic.get("Pivot")),
        "50-day MA": _safe_float(latest_indicators.get("MA50")),
        "200-day MA": _safe_float(latest_indicators.get("MA200")),
        "RSI (14)": _safe_float(latest_indicators.get("RSI (14)")),
        "Stochastic %K": _safe_float(latest_indicators.get("Stochastic %K")),
        "ATR (14)": _safe_float(latest_indicators.get("ATR (14)")),
        "ADX (14)": _safe_float(latest_indicators.get("ADX (14)")),
        "CCI (14)": _safe_float(latest_indicators.get("CCI (14)")),
        "Williams %R": _safe_float(latest_indicators.get("Williams %R")),
        "Ultimate Oscillator": _safe_float(
            latest_indicators.get("Ultimate Oscillator")
        ),
        "ROC (10)": _safe_float(latest_indicators.get("ROC (10)")),
        "BullBear Power": _safe_float(latest_indicators.get("BullBear Power")),
    }
    return row


def persist_ti_snapshot(
    *,
    ticker: str,
    asof_date: Any,
    latest_indicators: Mapping[str, Any],
    pivot_data: Any,
) -> Path:
    out_dir = paths.OUT_I_CALC_TI_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    t = _sanitize_ticker_for_filename(ticker)
    out_path = out_dir / f"{t}.csv"

    row = _ti_row_from_snapshot(
        asof_date=asof_date,
        latest_indicators=latest_indicators,
        pivot_data=pivot_data,
    )

    existing = _read_csv_if_exists(out_path)
    merged = _upsert_by_key(existing, row, key_col="Date")
    merged = _sort_by_date(merged)
    merged = cast(pd.DataFrame, merged.reindex(columns=TI_COLUMNS))
    merged.to_csv(out_path, index=False)
    return out_path


def _pp_columns() -> List[str]:
    cols: List[str] = ["Date"]
    for method in PP_METHODS:
        for level in PP_LEVELS:
            cols.append(f"{level}({method})")
    return cols


def _normalize_pp_level(level: str) -> str:
    if level == "Pivot Points":
        return "Pivot"
    return level


def _pp_row_from_snapshot(*, asof_date: Any, pivot_data: Any) -> Dict[str, Any]:
    pivots = _pivot_to_mapping(pivot_data)
    row: Dict[str, Any] = {"Date": _safe_date_text(asof_date)}
    for method in PP_METHODS:
        method_map = pivots.get(method, {}) if isinstance(pivots, dict) else {}
        for level in PP_LEVELS:
            key = _normalize_pp_level(level)
            value = None
            if isinstance(method_map, Mapping):
                value = method_map.get(key)
            if value is None or (isinstance(value, float) and not np.isfinite(value)):
                row[f"{level}({method})"] = "-"
            else:
                row[f"{level}({method})"] = float(value)
    return row


def persist_pp_snapshot(*, ticker: str, asof_date: Any, pivot_data: Any) -> Path:
    out_dir = paths.OUT_I_CALC_PP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    t = _sanitize_ticker_for_filename(ticker)
    out_path = out_dir / f"{t}.csv"

    row = _pp_row_from_snapshot(asof_date=asof_date, pivot_data=pivot_data)
    existing = _read_csv_if_exists(out_path)
    merged = _upsert_by_key(existing, row, key_col="Date")
    merged = _sort_by_date(merged)
    merged = cast(pd.DataFrame, merged.reindex(columns=_pp_columns()))
    merged.to_csv(out_path, index=False)
    return out_path


def _extract_model_values(
    model_results: Mapping[str, Optional[pd.DataFrame]],
    *,
    model_key: str,
    pred_col: str,
    lower_col: Optional[str] = None,
    upper_col: Optional[str] = None,
) -> Tuple[float, float, float]:
    df = model_results.get(model_key)
    if df is None or df.empty or pred_col not in df.columns:
        return float("nan"), float("nan"), float("nan")

    last = df.iloc[-1]
    pred = _safe_float(last.get(pred_col))
    lower = _safe_float(last.get(lower_col)) if lower_col else float("nan")
    upper = _safe_float(last.get(upper_col)) if upper_col else float("nan")
    return pred, lower, upper


def _ml_rows_from_model_results(
    *,
    ticker: str,
    model_results: Mapping[str, Optional[pd.DataFrame]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    torch_pred, _, _ = _extract_model_values(
        model_results, model_key="TorchForecast", pred_col="TorchForecast_Pred"
    )
    arimax_pred, arimax_lower, arimax_upper = _extract_model_values(
        model_results,
        model_key="ARIMAX",
        pred_col="ARIMAX_Pred",
        lower_col="ARIMAX_Lower",
        upper_col="ARIMAX_Upper",
    )
    pce_pred, pce_lower, pce_upper = _extract_model_values(
        model_results,
        model_key="PCE",
        pred_col="PCE_Pred",
        lower_col="PCE_Lower",
        upper_col="PCE_Upper",
    )
    lstm_pred, lstm_lower, lstm_upper = _extract_model_values(
        model_results,
        model_key="LSTM",
        pred_col="LSTM_Pred",
        lower_col="LSTM_Lower",
        upper_col="LSTM_Upper",
    )
    garch_pred, _, _ = _extract_model_values(
        model_results, model_key="GARCH", pred_col="GARCH_Pred"
    )
    var_pred, _, _ = _extract_model_values(
        model_results, model_key="VAR", pred_col="VAR_Pred"
    )
    rw_pred, _, _ = _extract_model_values(
        model_results, model_key="RW", pred_col="RW_Pred"
    )
    ets_pred, _, _ = _extract_model_values(
        model_results, model_key="ETS", pred_col="ETS_Pred"
    )
    dyna_pred, _, _ = _extract_model_values(
        model_results, model_key="DYNAMIX", pred_col="DYNAMIX_Pred"
    )
    dyna2_pred, _, _ = _extract_model_values(
        model_results, model_key="DYNAMIX_NONSTATIONARY", pred_col="DYNAMIX_Pred"
    )

    dyna_main = dyna_pred if np.isfinite(dyna_pred) else dyna2_pred

    row_main: Dict[str, Any] = {
        "Ticker": str(ticker).strip(),
        "Torch": torch_pred,
        "ARIMAX": arimax_pred,
        "PCE": pce_pred,
        "LSTM": lstm_pred,
        "GARCH": garch_pred,
        "VAR": var_pred,
        "RW": rw_pred,
        "ETS": ets_pred,
        "DynaMix": dyna_main,
    }

    row_meta: Dict[str, Any] = {
        **row_main,
        "ARIMAX_Lower": arimax_lower,
        "ARIMAX_Upper": arimax_upper,
        "PCE_Lower": pce_lower,
        "PCE_Upper": pce_upper,
        "LSTM_Lower": lstm_lower,
        "LSTM_Upper": lstm_upper,
        "DynaMix_Secondary": dyna2_pred,
    }
    return row_main, row_meta


def _fmt_point(x: Any) -> str:
    f = _safe_float(x)
    return f"{f:.4f}" if np.isfinite(f) else "-"


def _fmt_ci(point: Any, lower: Any, upper: Any) -> str:
    p = _safe_float(point)
    l = _safe_float(lower)
    u = _safe_float(upper)
    if np.isfinite(l) and np.isfinite(u) and np.isfinite(p):
        return f"{l:.4f}-{u:.4f}  <br> ~{p:.4f}"
    return _fmt_point(p)


def _fmt_dynamix(primary: Any, secondary: Any) -> str:
    p = _safe_float(primary)
    s = _safe_float(secondary)
    if np.isfinite(p) and np.isfinite(s):
        return f"{p:.6f} <br> {s:.6f}"
    if np.isfinite(p):
        return f"{p:.6f}"
    if np.isfinite(s):
        return f"{s:.6f}"
    return "-"


def _build_ml_markdown(meta_df: pd.DataFrame) -> str:
    header = [
        "|  Model | Torch | ARIMAX | PCE | LSTM  | GARCH  | VAR | Random-walk|  ETS  | Dyna |",
        "|:-------:|:-----:|:-------:|:-------:|:-------:|:-------:|------:|------:|------:|------:|",
    ]
    lines = list(header)

    for _, row in meta_df.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        lines.append(
            "| "
            + " | ".join(
                [
                    ticker,
                    _fmt_point(row.get("Torch")),
                    _fmt_ci(
                        row.get("ARIMAX"),
                        row.get("ARIMAX_Lower"),
                        row.get("ARIMAX_Upper"),
                    ),
                    _fmt_ci(
                        row.get("PCE"),
                        row.get("PCE_Lower"),
                        row.get("PCE_Upper"),
                    ),
                    _fmt_ci(
                        row.get("LSTM"),
                        row.get("LSTM_Lower"),
                        row.get("LSTM_Upper"),
                    ),
                    _fmt_point(row.get("GARCH")),
                    _fmt_point(row.get("VAR")),
                    _fmt_point(row.get("RW")),
                    _fmt_point(row.get("ETS")),
                    _fmt_dynamix(row.get("DynaMix"), row.get("DynaMix_Secondary")),
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n"


def persist_ml_snapshots(
    *,
    ticker: str,
    asof_date: Any,
    model_results: Mapping[str, Optional[pd.DataFrame]],
    ticker_order: Optional[Iterable[str]] = None,
) -> Tuple[Path, Path]:
    out_dir = paths.OUT_I_CALC_ML_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    date_tag = _safe_date_text(asof_date)
    csv_path = out_dir / f"ML_{date_tag}.csv"
    md_path = out_dir / f"ML_{date_tag}.md"
    meta_path = out_dir / f"ML_{date_tag}_meta.csv"

    row_main, row_meta = _ml_rows_from_model_results(
        ticker=ticker,
        model_results=model_results,
    )

    main_df = _read_csv_if_exists(csv_path)
    main_df = _upsert_by_key(main_df, row_main, key_col=ML_TICKER_COL)
    main_df = cast(pd.DataFrame, main_df.reindex(columns=ML_MAIN_COLUMNS))

    meta_df = _read_csv_if_exists(meta_path)
    meta_df = _upsert_by_key(meta_df, row_meta, key_col=ML_TICKER_COL)
    meta_df = cast(pd.DataFrame, meta_df.reindex(columns=ML_META_COLUMNS))

    order = list(ticker_order) if ticker_order is not None else []
    if order:
        main_df = _sort_by_ticker_order(main_df, order)
        meta_df = _sort_by_ticker_order(meta_df, order)
    else:
        main_df = cast(
            pd.DataFrame, main_df.sort_values(by=[ML_TICKER_COL], kind="stable")
        )
        main_df = cast(pd.DataFrame, main_df.reset_index(drop=True))
        meta_df = cast(
            pd.DataFrame, meta_df.sort_values(by=[ML_TICKER_COL], kind="stable")
        )
        meta_df = cast(pd.DataFrame, meta_df.reset_index(drop=True))

    main_df.to_csv(csv_path, index=False)
    meta_df.to_csv(meta_path, index=False)
    md_path.write_text(_build_ml_markdown(meta_df), encoding="utf-8")

    return csv_path, md_path


__all__ = [
    "persist_ti_snapshot",
    "persist_pp_snapshot",
    "persist_ml_snapshots",
]
