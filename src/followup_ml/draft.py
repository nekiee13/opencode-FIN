from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd

from src.config import paths
from src.data.loading import fetch_data, resolve_raw_csv_path
from src.exo.exo_config import load_exo_config
from src.models import compat_api as models_api

log = logging.getLogger(__name__)


ROUND_STATE_DRAFT_T0 = "DRAFT_T0"
ROUND_STATE_PARTIAL_ACTUALS = "PARTIAL_ACTUALS"
ROUND_STATE_FINAL_TPLUS3 = "FINAL_TPLUS3"
ROUND_STATE_REVISED = "REVISED"

SCHEMA_VERSION = "followup-ml-v1"
DEFAULT_FH = 3

TICKER_ORDER_DEFAULT: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
RUNTIME_TICKER_MAP: Dict[str, str] = {"SPX": "GSPC"}

MODEL_ORDER: Sequence[str] = (
    "Torch",
    "DYNAMIX",
    "ARIMAX",
    "PCE",
    "LSTM",
    "GARCH",
    "VAR",
    "RW",
    "ETS",
)

MODEL_COLUMNS: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {
    "Torch": ("TorchForecast_Pred", "TorchForecast_Lower", "TorchForecast_Upper"),
    "DYNAMIX": ("DYNAMIX_Pred", "DYNAMIX_Lower", "DYNAMIX_Upper"),
    "ARIMAX": ("ARIMAX_Pred", "ARIMAX_Lower", "ARIMAX_Upper"),
    "PCE": ("PCE_Pred", "PCE_Lower", "PCE_Upper"),
    "LSTM": ("LSTM_Pred", "LSTM_Lower", "LSTM_Upper"),
    "GARCH": ("GARCH_Pred", None, None),
    "VAR": ("VAR_Pred", None, None),
    "RW": ("RW_Pred", None, None),
    "ETS": ("ETS_Pred", None, None),
}


@dataclass(frozen=True)
class DraftArtifacts:
    round_id: str
    round_dir: Path
    forecasts_csv: Path
    draft_metrics_csv: Path
    day3_matrix_csv: Path
    context_json: Path
    dashboard_md: Path


@dataclass(frozen=True)
class FinalizeArtifacts:
    round_id: str
    round_state: str
    ok_actuals: int
    total_actuals: int
    actuals_csv: Path
    context_json: Path
    dashboard_md: Path


def _discover_fh() -> int:
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _canonical_tickers(tickers: Optional[Iterable[str]] = None) -> List[str]:
    if tickers is None:
        return list(TICKER_ORDER_DEFAULT)
    out: List[str] = []
    for t in tickers:
        t_norm = str(t).strip().upper().replace("^", "")
        if t_norm == "GSPC":
            t_norm = "SPX"
        if t_norm and t_norm not in out:
            out.append(t_norm)
    return out or list(TICKER_ORDER_DEFAULT)


def _runtime_ticker(logical_ticker: str) -> str:
    return RUNTIME_TICKER_MAP.get(logical_ticker, logical_ticker)


def _to_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    out = cast(pd.DataFrame, df.copy())
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
    out = cast(pd.DataFrame, out.loc[~out.index.isna(), :].copy())
    if not out.index.is_monotonic_increasing:
        out = cast(pd.DataFrame, out.sort_index())
    return out


def _to_float_or_nan(v: Any) -> float:
    try:
        f = float(v)
        if np.isfinite(f):
            return f
    except Exception:
        pass
    return float("nan")


def _load_exo_config_optional(fh: int) -> Optional[Any]:
    exo_path = paths.get_exo_config_path()
    if not exo_path.exists():
        return None
    try:
        return load_exo_config(exo_path, forecast_horizon=fh)
    except Exception as e:
        log.warning("Failed to load exogenous config at %s: %s", exo_path, e)
        return None


def _extract_forecast_df(obj: Any) -> Optional[pd.DataFrame]:
    """
    Normalize heterogeneous model return types to a forecast DataFrame.

    Known shapes from compat_api include:
    - DataFrame
    - tuple(DataFrame, ...)
    - None
    """
    if obj is None:
        return None

    if isinstance(obj, pd.DataFrame):
        return obj

    if isinstance(obj, tuple):
        for item in obj:
            if isinstance(item, pd.DataFrame):
                return item

    return None


def _run_models_for_ticker(
    logical_ticker: str,
    *,
    fh: int,
    exo_config: Optional[Any],
) -> Dict[str, Optional[pd.DataFrame]]:
    runtime_ticker = _runtime_ticker(logical_ticker)
    out: Dict[str, Optional[pd.DataFrame]] = {k: None for k in MODEL_ORDER}

    try:
        out["Torch"] = _extract_forecast_df(
            models_api.run_external_torch_forecasting(runtime_ticker)
        )
    except Exception as e:
        log.warning("Torch failed for %s: %s", logical_ticker, e)

    enriched: Optional[pd.DataFrame]
    try:
        enriched = models_api.run_external_ti_calculator(runtime_ticker)
    except Exception as e:
        enriched = None
        log.warning("TI worker failed for %s: %s", logical_ticker, e)

    if enriched is None or enriched.empty:
        return out

    try:
        out["DYNAMIX"] = _extract_forecast_df(
            models_api.predict_dynamix(
                enriched, ticker=runtime_ticker, fh=fh, fit_nonstationary=False
            )
        )
    except Exception as e:
        log.warning("DYNAMIX failed for %s: %s", logical_ticker, e)

    try:
        arimax_df, _, _ = models_api.predict_arima(
            enriched, ticker=runtime_ticker, exo_config=exo_config
        )
        out["ARIMAX"] = _extract_forecast_df(arimax_df)
    except Exception as e:
        log.warning("ARIMAX failed for %s: %s", logical_ticker, e)

    try:
        out["PCE"] = _extract_forecast_df(
            models_api.predict_pce_narx(
                enriched, ticker=runtime_ticker, exo_config=exo_config
            )
        )
    except Exception as e:
        log.warning("PCE failed for %s: %s", logical_ticker, e)

    try:
        out["LSTM"] = _extract_forecast_df(
            models_api.predict_lstm(enriched, ticker=runtime_ticker, exo_config=exo_config)
        )
    except Exception as e:
        log.warning("LSTM failed for %s: %s", logical_ticker, e)

    try:
        out["GARCH"] = _extract_forecast_df(
            models_api.predict_arch_model(
                enriched, ticker=runtime_ticker, exo_config=exo_config
            )
        )
    except Exception as e:
        log.warning("GARCH failed for %s: %s", logical_ticker, e)

    try:
        out["VAR"] = _extract_forecast_df(models_api.predict_var(enriched))
    except Exception as e:
        log.warning("VAR failed for %s: %s", logical_ticker, e)

    try:
        out["RW"] = _extract_forecast_df(models_api.predict_random_walk(enriched))
    except Exception as e:
        log.warning("RW failed for %s: %s", logical_ticker, e)

    try:
        out["ETS"] = _extract_forecast_df(models_api.predict_exp_smoothing(enriched))
    except Exception as e:
        log.warning("ETS failed for %s: %s", logical_ticker, e)

    return out


def _rows_for_model_forecast(
    *,
    round_id: str,
    round_state: str,
    logical_ticker: str,
    runtime_ticker: str,
    model: str,
    df: Optional[pd.DataFrame],
    fh: int,
    generated_at: str,
) -> List[Dict[str, Any]]:
    pred_col, lower_col, upper_col = MODEL_COLUMNS[model]
    rows: List[Dict[str, Any]] = []

    if df is None or df.empty:
        for step in range(1, fh + 1):
            rows.append(
                {
                    "round_id": round_id,
                    "round_state": round_state,
                    "ticker": logical_ticker,
                    "runtime_ticker": runtime_ticker,
                    "model": model,
                    "fh_step": step,
                    "forecast_date": "",
                    "pred_value": np.nan,
                    "lower_ci": np.nan,
                    "upper_ci": np.nan,
                    "status": "model_unavailable",
                    "generated_at": generated_at,
                }
            )
        return rows

    xdf = _to_datetime_index(df)
    if pred_col not in xdf.columns:
        for step in range(1, fh + 1):
            rows.append(
                {
                    "round_id": round_id,
                    "round_state": round_state,
                    "ticker": logical_ticker,
                    "runtime_ticker": runtime_ticker,
                    "model": model,
                    "fh_step": step,
                    "forecast_date": "",
                    "pred_value": np.nan,
                    "lower_ci": np.nan,
                    "upper_ci": np.nan,
                    "status": f"missing_col:{pred_col}",
                    "generated_at": generated_at,
                }
            )
        return rows

    for step in range(1, fh + 1):
        i = step - 1
        if i >= len(xdf):
            rows.append(
                {
                    "round_id": round_id,
                    "round_state": round_state,
                    "ticker": logical_ticker,
                    "runtime_ticker": runtime_ticker,
                    "model": model,
                    "fh_step": step,
                    "forecast_date": "",
                    "pred_value": np.nan,
                    "lower_ci": np.nan,
                    "upper_ci": np.nan,
                    "status": "short_horizon",
                    "generated_at": generated_at,
                }
            )
            continue

        row = cast(pd.Series, xdf.iloc[i])
        dt = cast(pd.Timestamp, xdf.index[i])
        pred_v = _to_float_or_nan(row.get(pred_col))
        low_v = _to_float_or_nan(row.get(lower_col)) if lower_col else np.nan
        up_v = _to_float_or_nan(row.get(upper_col)) if upper_col else np.nan
        status = "ok" if np.isfinite(pred_v) else "nan_pred"

        rows.append(
            {
                "round_id": round_id,
                "round_state": round_state,
                "ticker": logical_ticker,
                "runtime_ticker": runtime_ticker,
                "model": model,
                "fh_step": step,
                "forecast_date": dt.strftime("%Y-%m-%d"),
                "pred_value": pred_v,
                "lower_ci": low_v,
                "upper_ci": up_v,
                "status": status,
                "generated_at": generated_at,
            }
        )

    return rows


def _build_dayn_matrix(forecasts_df: pd.DataFrame, *, fh_step: int) -> pd.DataFrame:
    sub = cast(
        pd.DataFrame,
        forecasts_df[
            (forecasts_df["fh_step"] == int(fh_step)) & (forecasts_df["status"] == "ok")
        ][["ticker", "model", "pred_value"]].copy(),
    )
    if sub.empty:
        return pd.DataFrame(columns=["ticker", *MODEL_ORDER])
    piv = cast(
        pd.DataFrame,
        sub.pivot_table(
            index="ticker", columns="model", values="pred_value", aggfunc="first"
        ).reset_index(),
    )
    for m in MODEL_ORDER:
        if m not in piv.columns:
            piv[m] = np.nan
    cols = ["ticker", *MODEL_ORDER]
    piv = cast(pd.DataFrame, piv[cols].copy())
    return piv


def _build_draft_metrics(dayn_df: pd.DataFrame) -> pd.DataFrame:
    if dayn_df.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "available_models",
                "day3_min",
                "day3_max",
                "day3_spread",
                "day3_median",
            ]
        )

    rows: List[Dict[str, Any]] = []
    for _, rec in dayn_df.iterrows():
        ticker = str(rec["ticker"])
        vals = [
            float(rec[m])
            for m in MODEL_ORDER
            if m in rec and pd.notna(rec[m]) and np.isfinite(float(rec[m]))
        ]
        if vals:
            vmin = float(min(vals))
            vmax = float(max(vals))
            spread = float(vmax - vmin)
            median = float(np.median(np.array(vals, dtype=float)))
            available = int(len(vals))
        else:
            vmin = np.nan
            vmax = np.nan
            spread = np.nan
            median = np.nan
            available = 0

        rows.append(
            {
                "ticker": ticker,
                "available_models": available,
                "day3_min": vmin,
                "day3_max": vmax,
                "day3_spread": spread,
                "day3_median": median,
            }
        )

    out = pd.DataFrame(rows)
    return cast(pd.DataFrame, out)


def _fmt_number(v: Any, ndp: int = 4) -> str:
    try:
        f = float(v)
        if np.isfinite(f):
            return f"{f:.{ndp}f}"
    except Exception:
        pass
    return "-"


def _render_round_markdown(
    *,
    round_id: str,
    round_state: str,
    generated_at: str,
    fh: int,
    dayn_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    actuals_df: Optional[pd.DataFrame] = None,
) -> str:
    lines: List[str] = []
    lines.append(f"# Follow-up ML Board - {round_id}")
    lines.append("")
    lines.append(f"- State: `{round_state}`")
    lines.append(f"- Generated at: `{generated_at}`")
    lines.append(f"- Forecast horizon (FH): `{fh}`")
    if round_state == ROUND_STATE_DRAFT_T0:
        lines.append("- Accuracy/scoring fields: `Pending +3 actual values`")
    elif round_state == ROUND_STATE_PARTIAL_ACTUALS:
        lines.append("- Accuracy/scoring fields: `Partial +3 actual values available`")
    elif round_state == ROUND_STATE_FINAL_TPLUS3:
        lines.append("- Accuracy/scoring fields: `+3 actual values complete`")
    else:
        lines.append("- Accuracy/scoring fields: `Updated after revision`")
    lines.append("")
    lines.append(f"## T0 Forecast Matrix (Day {fh})")
    lines.append("")

    header = ["Ticker", *MODEL_ORDER, "Avail", "Spread"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join([":--" for _ in header]) + "|")

    m_by_ticker: Dict[str, Dict[str, Any]] = {}
    for _, r in metrics_df.iterrows():
        m_by_ticker[str(r["ticker"])] = dict(r)

    if dayn_df.empty:
        lines.append("| - | - |")
    else:
        for _, rec in dayn_df.iterrows():
            t = str(rec["ticker"])
            row_vals = [t]
            for m in MODEL_ORDER:
                row_vals.append(_fmt_number(rec.get(m), ndp=4))
            mm = m_by_ticker.get(t, {})
            row_vals.append(str(mm.get("available_models", 0)))
            row_vals.append(_fmt_number(mm.get("day3_spread"), ndp=4))
            lines.append("| " + " | ".join(row_vals) + " |")

    if actuals_df is not None and not actuals_df.empty:
        lines.append("")
        lines.append("## +3 Actuals Ingestion")
        lines.append("")
        header2 = ["Ticker", "Expected", "Actual", "Status"]
        lines.append("| " + " | ".join(header2) + " |")
        lines.append("|" + "|".join([":--" for _ in header2]) + "|")
        for _, rec in actuals_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rec.get("ticker", "")),
                        str(rec.get("expected_actual_date", "")),
                        _fmt_number(rec.get("actual_close"), ndp=4),
                        str(rec.get("status", "")),
                    ]
                )
                + " |"
            )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This board is generated from persisted round artifacts under out/i_calc.")
    lines.append(
        "- Final scoring transformation and AVR feedback are applied in the finalization stage."
    )
    lines.append("")
    return "\n".join(lines)


def _render_t0_markdown(
    *,
    round_id: str,
    generated_at: str,
    fh: int,
    dayn_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
) -> str:
    return _render_round_markdown(
        round_id=round_id,
        round_state=ROUND_STATE_DRAFT_T0,
        generated_at=generated_at,
        fh=fh,
        dayn_df=dayn_df,
        metrics_df=metrics_df,
        actuals_df=None,
    )


def _write_nonempty_text(path: Path, content: str) -> None:
    """Write text content and guarantee non-empty file output."""
    safe = content
    if not isinstance(safe, str) or not safe.strip():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe = (
            "# Follow-up ML Board\n\n"
            f"- Generated at: `{now}`\n"
            "- Note: renderer produced empty content; fallback body written.\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe, encoding="utf-8")


def _round_dir(round_id: str) -> Path:
    return (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / str(round_id)).resolve()


def _round_actuals_path(round_id: str) -> Path:
    return _round_dir(round_id) / "actuals_tplus3.csv"


def _global_actuals_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_ACTUALS_DIR / f"{round_id}_actuals.csv"


def _expected_actual_dates_by_ticker(
    forecasts_df: pd.DataFrame,
    *,
    fh: int,
    tickers: Sequence[str],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for t in tickers:
        sub = cast(
            pd.DataFrame,
            forecasts_df[
                (forecasts_df["ticker"] == t)
                & (forecasts_df["fh_step"] == int(fh))
                & (forecasts_df["forecast_date"].astype(str).str.len() > 0)
            ][["forecast_date"]],
        )
        if sub.empty:
            out[t] = ""
            continue
        vc = cast(pd.Series, sub["forecast_date"].astype(str).value_counts())
        out[t] = str(vc.index[0]) if len(vc.index) > 0 else ""
    return out


def _lookup_actual_close_for_date(runtime_ticker: str, expected_date: str) -> Tuple[float, str, str]:
    csv_path = resolve_raw_csv_path(runtime_ticker)
    df = fetch_data(runtime_ticker, csv_path=csv_path)
    if df is None or df.empty or "Close" not in df.columns:
        return np.nan, "data_unavailable", str(csv_path)

    xdf = _to_datetime_index(df)
    if xdf.empty:
        return np.nan, "data_unavailable", str(csv_path)

    idx_date = cast(pd.Series, xdf.index.to_series().dt.strftime("%Y-%m-%d"))
    mask = idx_date == str(expected_date)
    if not bool(mask.any()):
        return np.nan, "actual_missing", str(csv_path)

    matched = cast(pd.DataFrame, xdf.loc[mask.values].copy())
    if matched.empty:
        return np.nan, "actual_missing", str(csv_path)

    close_v = _to_float_or_nan(cast(pd.Series, matched["Close"]).iloc[-1])
    if not np.isfinite(close_v):
        return np.nan, "actual_nan", str(csv_path)

    return float(close_v), "ok", str(csv_path)


def _actuals_changed(prev_df: pd.DataFrame, new_df: pd.DataFrame) -> bool:
    base_cols = ["ticker", "expected_actual_date", "status", "actual_close"]
    p = cast(pd.DataFrame, prev_df.loc[:, [c for c in base_cols if c in prev_df.columns]].copy())
    n = cast(pd.DataFrame, new_df.loc[:, [c for c in base_cols if c in new_df.columns]].copy())
    if "actual_close" in p.columns:
        p["actual_close"] = pd.to_numeric(p["actual_close"], errors="coerce").round(8)
    if "actual_close" in n.columns:
        n["actual_close"] = pd.to_numeric(n["actual_close"], errors="coerce").round(8)
    p = cast(pd.DataFrame, p.sort_values(by=["ticker"]).reset_index(drop=True))
    n = cast(pd.DataFrame, n.sort_values(by=["ticker"]).reset_index(drop=True))
    return not p.equals(n)


def run_tplus3_finalize_round(
    *,
    round_id: str,
    tickers: Optional[Iterable[str]] = None,
) -> FinalizeArtifacts:
    """
    Ingest +3 actual values for a round and update round state.

    State policy:
    - no actuals found: DRAFT_T0
    - partial actuals: PARTIAL_ACTUALS
    - all actuals found: FINAL_TPLUS3
    - if previously FINAL/REVISED and values changed: REVISED
    """
    paths.ensure_directories()

    round_dir = _round_dir(round_id)
    context_json = round_dir / "round_context.json"
    forecasts_csv = round_dir / "t0_forecasts.csv"
    draft_metrics_csv = round_dir / "t0_draft_metrics.csv"

    if not context_json.exists() or not forecasts_csv.exists() or not draft_metrics_csv.exists():
        raise FileNotFoundError(
            f"Round artifacts missing for {round_id}. Expected files in {round_dir}."
        )

    context = json.loads(context_json.read_text(encoding="utf-8"))
    prev_state = str(context.get("round_state", ROUND_STATE_DRAFT_T0))
    fh_i = int(context.get("fh", DEFAULT_FH))

    forecasts_df = pd.read_csv(forecasts_csv)
    ticker_list = _canonical_tickers(tickers or context.get("tickers", TICKER_ORDER_DEFAULT))
    expected_dates = _expected_actual_dates_by_ticker(
        cast(pd.DataFrame, forecasts_df), fh=fh_i, tickers=ticker_list
    )

    rows: List[Dict[str, Any]] = []
    for t in ticker_list:
        runtime_t = _runtime_ticker(t)
        expected_date = str(expected_dates.get(t, ""))
        if not expected_date:
            rows.append(
                {
                    "round_id": str(round_id),
                    "ticker": t,
                    "runtime_ticker": runtime_t,
                    "expected_actual_date": "",
                    "actual_close": np.nan,
                    "status": "no_expected_date",
                    "source_csv": "",
                }
            )
            continue

        actual_v, status, source_csv = _lookup_actual_close_for_date(runtime_t, expected_date)
        rows.append(
            {
                "round_id": str(round_id),
                "ticker": t,
                "runtime_ticker": runtime_t,
                "expected_actual_date": expected_date,
                "actual_close": actual_v,
                "status": status,
                "source_csv": source_csv,
            }
        )

    actuals_df = pd.DataFrame(rows)
    ok_count = int((actuals_df["status"] == "ok").sum()) if not actuals_df.empty else 0
    total = int(len(actuals_df))

    if ok_count <= 0:
        round_state = ROUND_STATE_DRAFT_T0
    elif ok_count < total:
        round_state = ROUND_STATE_PARTIAL_ACTUALS
    else:
        round_state = ROUND_STATE_FINAL_TPLUS3

    prev_actuals_path = _round_actuals_path(round_id)
    if (
        prev_actuals_path.exists()
        and prev_state in {ROUND_STATE_FINAL_TPLUS3, ROUND_STATE_REVISED}
        and round_state == ROUND_STATE_FINAL_TPLUS3
    ):
        prev_actuals_df = pd.read_csv(prev_actuals_path)
        if _actuals_changed(cast(pd.DataFrame, prev_actuals_df), cast(pd.DataFrame, actuals_df)):
            round_state = ROUND_STATE_REVISED

    round_actuals_csv = _round_actuals_path(round_id)
    global_actuals_csv = _global_actuals_path(round_id)
    round_actuals_csv.parent.mkdir(parents=True, exist_ok=True)
    global_actuals_csv.parent.mkdir(parents=True, exist_ok=True)
    cast(pd.DataFrame, actuals_df).to_csv(round_actuals_csv, index=False)
    cast(pd.DataFrame, actuals_df).to_csv(global_actuals_csv, index=False)

    context["round_state"] = round_state
    context["finalized_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context["actuals"] = {
        "ok_count": ok_count,
        "total": total,
        "actuals_csv": str(round_actuals_csv),
        "global_actuals_csv": str(global_actuals_csv),
    }
    context_outputs = cast(Dict[str, Any], context.get("outputs", {}))
    context_outputs["actuals_csv"] = str(round_actuals_csv)
    context_outputs["global_actuals_csv"] = str(global_actuals_csv)
    context["outputs"] = context_outputs
    context_json.write_text(json.dumps(context, indent=2), encoding="utf-8")

    metrics_df = pd.read_csv(draft_metrics_csv)
    dayn_df = _build_dayn_matrix(cast(pd.DataFrame, forecasts_df), fh_step=fh_i)
    dashboard_md = paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{round_id}_draft.md"
    md = _render_round_markdown(
        round_id=str(round_id),
        round_state=round_state,
        generated_at=str(context.get("generated_at", "")),
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
        actuals_df=cast(pd.DataFrame, actuals_df),
    )
    _write_nonempty_text(dashboard_md, md)

    return FinalizeArtifacts(
        round_id=str(round_id),
        round_state=round_state,
        ok_actuals=ok_count,
        total_actuals=total,
        actuals_csv=round_actuals_csv,
        context_json=context_json,
        dashboard_md=dashboard_md,
    )


def run_t0_draft_round(
    *,
    round_id: str,
    tickers: Optional[Iterable[str]] = None,
    fh: Optional[int] = None,
) -> DraftArtifacts:
    """
    Build and persist a draft follow-up round (T0, no +3 actual values).
    """
    paths.ensure_directories()

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    ticker_list = _canonical_tickers(tickers)
    exo_config = _load_exo_config_optional(fh_i)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_rows: List[Dict[str, Any]] = []
    for logical_ticker in ticker_list:
        runtime_t = _runtime_ticker(logical_ticker)
        forecasts = _run_models_for_ticker(
            logical_ticker, fh=fh_i, exo_config=exo_config
        )
        for model in MODEL_ORDER:
            all_rows.extend(
                _rows_for_model_forecast(
                    round_id=round_id,
                    round_state=ROUND_STATE_DRAFT_T0,
                    logical_ticker=logical_ticker,
                    runtime_ticker=runtime_t,
                    model=model,
                    df=forecasts.get(model),
                    fh=fh_i,
                    generated_at=generated_at,
                )
            )

    forecasts_df = pd.DataFrame(all_rows)
    dayn_df = _build_dayn_matrix(forecasts_df, fh_step=fh_i)
    metrics_df = _build_draft_metrics(dayn_df)

    round_dir = _round_dir(round_id)
    round_dir.mkdir(parents=True, exist_ok=True)

    forecasts_csv = round_dir / "t0_forecasts.csv"
    draft_metrics_csv = round_dir / "t0_draft_metrics.csv"
    day3_matrix_csv = round_dir / f"t0_day{fh_i}_matrix.csv"
    context_json = round_dir / "round_context.json"
    dashboard_md = paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{round_id}_draft.md"

    cast(pd.DataFrame, forecasts_df).to_csv(forecasts_csv, index=False)
    cast(pd.DataFrame, metrics_df).to_csv(draft_metrics_csv, index=False)
    cast(pd.DataFrame, dayn_df).to_csv(day3_matrix_csv, index=False)

    context: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "round_id": str(round_id),
        "round_state": ROUND_STATE_DRAFT_T0,
        "generated_at": generated_at,
        "fh": int(fh_i),
        "tickers": ticker_list,
        "models": list(MODEL_ORDER),
        "exo_config_path": str(paths.get_exo_config_path()),
        "outputs": {
            "forecasts_csv": str(forecasts_csv),
            "draft_metrics_csv": str(draft_metrics_csv),
            "dayn_matrix_csv": str(day3_matrix_csv),
            "dashboard_md": str(dashboard_md),
        },
    }
    context_json.write_text(json.dumps(context, indent=2), encoding="utf-8")

    dashboard_md.parent.mkdir(parents=True, exist_ok=True)
    md = _render_t0_markdown(
        round_id=round_id,
        generated_at=generated_at,
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
    )
    _write_nonempty_text(dashboard_md, md)

    return DraftArtifacts(
        round_id=str(round_id),
        round_dir=round_dir,
        forecasts_csv=forecasts_csv,
        draft_metrics_csv=draft_metrics_csv,
        day3_matrix_csv=day3_matrix_csv,
        context_json=context_json,
        dashboard_md=dashboard_md,
    )


def render_t0_dashboard_for_round(round_id: str) -> Path:
    """
    Re-render markdown dashboard from persisted round artifacts.
    """
    round_dir = _round_dir(round_id)
    context_json = round_dir / "round_context.json"
    forecasts_csv = round_dir / "t0_forecasts.csv"
    draft_metrics_csv = round_dir / "t0_draft_metrics.csv"

    if not context_json.exists() or not forecasts_csv.exists() or not draft_metrics_csv.exists():
        raise FileNotFoundError(
            f"Round artifacts missing for {round_id}. Expected files in {round_dir}."
        )

    context = json.loads(context_json.read_text(encoding="utf-8"))
    fh_i = int(context.get("fh", DEFAULT_FH))
    generated_at = str(context.get("generated_at", ""))
    round_state = str(context.get("round_state", ROUND_STATE_DRAFT_T0))

    forecasts_df = pd.read_csv(forecasts_csv)
    metrics_df = pd.read_csv(draft_metrics_csv)
    dayn_df = _build_dayn_matrix(cast(pd.DataFrame, forecasts_df), fh_step=fh_i)
    actuals_path = _round_actuals_path(round_id)
    actuals_df: Optional[pd.DataFrame] = None
    if actuals_path.exists():
        actuals_df = pd.read_csv(actuals_path)

    md = _render_round_markdown(
        round_id=str(round_id),
        round_state=round_state,
        generated_at=generated_at,
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
        actuals_df=cast(Optional[pd.DataFrame], actuals_df),
    )
    dashboard_md = paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{round_id}_draft.md"
    _write_nonempty_text(dashboard_md, md)
    return dashboard_md
