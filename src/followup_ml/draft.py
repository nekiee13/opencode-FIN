from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

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
    weighted_ensemble_csv: Path
    context_json: Path
    dashboard_md: Path


@dataclass(frozen=True)
class FinalizeArtifacts:
    round_id: str
    round_state: str
    run_mode: str
    lookup_date_override: str
    ok_actuals: int
    total_actuals: int
    scored_rows: int
    mapped_rows: int
    total_score_rows: int
    model_coverage_avg: float
    actuals_csv: Path
    partial_scores_csv: Path
    model_summary_csv: Path
    avr_history_csv: Path
    avr_summary_csv: Path
    next_weights_csv: Path
    context_json: Path
    dashboard_md: Path


NAN = float("nan")


def _isfinite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def _median(vals: Sequence[float]) -> float:
    try:
        return float(statistics.median([float(v) for v in vals]))
    except Exception:
        return NAN


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
        if _isfinite(f):
            return f
    except Exception:
        pass
    return NAN


def _load_exo_config_optional(fh: int) -> Optional[Any]:
    exo_path = paths.get_exo_config_path()
    if not exo_path.exists():
        return None
    try:
        return load_exo_config(exo_path, forecast_horizon=fh)
    except Exception as e:
        log.warning("Failed to load exogenous config at %s: %s", exo_path, e)
        return None


def _resolve_value_assign_path() -> Path:
    env_path = os.getenv("FIN_FOLLOWUP_VALUE_ASSIGN")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return paths.FOLLOWUP_ML_VALUE_ASSIGN_PATH.resolve()


def _default_value_assign_table() -> pd.DataFrame:
    rows = [
        (0.0, 0.0),
        (50.0, 50.0),
        (70.0, 70.0),
        (80.0, 80.0),
        (90.0, 90.0),
        (95.0, 95.0),
        (97.0, 97.0),
        (98.0, 98.0),
        (99.0, 99.0),
        (99.5, 99.5),
        (99.75, 99.75),
        (99.9, 99.9),
        (99.99, 100.0),
    ]
    return pd.DataFrame(rows, columns=["value", "assign"])


def _load_value_assign_table() -> Tuple[pd.DataFrame, Path]:
    map_path = _resolve_value_assign_path()
    df: pd.DataFrame
    try:
        if map_path.exists():
            loaded = pd.read_csv(map_path)
            if "value" in loaded.columns and "assign" in loaded.columns:
                df = cast(pd.DataFrame, loaded[["value", "assign"]].copy())
            else:
                log.warning(
                    "Value->Assign table missing columns at %s; using defaults.",
                    map_path,
                )
                df = _default_value_assign_table()
        else:
            log.warning(
                "Value->Assign table not found at %s; using defaults.", map_path
            )
            df = _default_value_assign_table()
    except Exception as e:
        log.warning("Failed loading Value->Assign table at %s: %s", map_path, e)
        df = _default_value_assign_table()

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["assign"] = pd.to_numeric(df["assign"], errors="coerce")
    df = cast(pd.DataFrame, df.dropna(subset=["value", "assign"]))
    if df.empty:
        df = _default_value_assign_table()
    df = cast(
        pd.DataFrame,
        df.sort_values(by=["value"]).drop_duplicates(subset=["value"], keep="last"),
    )
    return df.reset_index(drop=True), map_path


def _lookup_assign_value(metric_value: float, mapping_df: pd.DataFrame) -> float:
    if not _isfinite(metric_value):
        return NAN
    if mapping_df.empty:
        return metric_value

    values = [float(v) for v in list(mapping_df["value"])]
    assigns = [float(a) for a in list(mapping_df["assign"])]
    if not values:
        return metric_value

    i = bisect_right(values, float(metric_value)) - 1
    if i < 0:
        i = 0
    if i >= len(assigns):
        i = len(assigns) - 1
    return float(assigns[i])


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
    history_mode: str = "live",
    as_of_date: Optional[str] = None,
) -> Dict[str, Optional[pd.DataFrame]]:
    runtime_ticker = _runtime_ticker(logical_ticker)
    out: Dict[str, Optional[pd.DataFrame]] = {k: None for k in MODEL_ORDER}

    try:
        out["Torch"] = _extract_forecast_df(
            models_api.run_external_torch_forecasting(
                runtime_ticker,
                history_mode=history_mode,
                as_of_date=as_of_date,
            )
        )
    except Exception as e:
        log.warning("Torch failed for %s: %s", logical_ticker, e)

    enriched: Optional[pd.DataFrame]
    try:
        enriched = models_api.run_external_ti_calculator(
            runtime_ticker,
            history_mode=history_mode,
            as_of_date=as_of_date,
        )
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
            models_api.predict_lstm(
                enriched,
                ticker=runtime_ticker,
                exo_config=exo_config,
                history_mode=history_mode,
            )
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
        out["VAR"] = _extract_forecast_df(
            models_api.predict_var(enriched, ticker=runtime_ticker)
        )
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
                    "pred_value": NAN,
                    "lower_ci": NAN,
                    "upper_ci": NAN,
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
                    "pred_value": NAN,
                    "lower_ci": NAN,
                    "upper_ci": NAN,
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
                    "pred_value": NAN,
                    "lower_ci": NAN,
                    "upper_ci": NAN,
                    "status": "short_horizon",
                    "generated_at": generated_at,
                }
            )
            continue

        row = cast(pd.Series, xdf.iloc[i])
        dt = cast(pd.Timestamp, xdf.index[i])
        pred_v = _to_float_or_nan(row.get(pred_col))
        low_v = _to_float_or_nan(row.get(lower_col)) if lower_col else NAN
        up_v = _to_float_or_nan(row.get(upper_col)) if upper_col else NAN
        status = "ok" if _isfinite(pred_v) else "nan_pred"

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
            piv[m] = NAN
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
            if m in rec and pd.notna(rec[m]) and _isfinite(float(rec[m]))
        ]
        if vals:
            vmin = float(min(vals))
            vmax = float(max(vals))
            spread = float(vmax - vmin)
            median = _median(vals)
            available = int(len(vals))
        else:
            vmin = NAN
            vmax = NAN
            spread = NAN
            median = NAN
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
        if _isfinite(f):
            return f"{f:.{ndp}f}"
    except Exception:
        pass
    return "-"


def _to_int_or_zero(v: Any) -> int:
    try:
        f = float(v)
        if _isfinite(f):
            return int(f)
    except Exception:
        pass
    return 0


def _render_round_markdown(
    *,
    round_id: str,
    round_state: str,
    generated_at: str,
    fh: int,
    dayn_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    actuals_df: Optional[pd.DataFrame] = None,
    score_summary_df: Optional[pd.DataFrame] = None,
    score_stats: Optional[Dict[str, Any]] = None,
    avr_summary_df: Optional[pd.DataFrame] = None,
    avr_stats: Optional[Dict[str, Any]] = None,
    weighted_ensemble_df: Optional[pd.DataFrame] = None,
    weights_source: Optional[Dict[str, Any]] = None,
    run_mode: str = "strict_production",
    lookup_date_override: str = "",
) -> str:
    lines: List[str] = []
    lines.append(f"# Follow-up ML Board - {round_id}")
    lines.append("")
    lines.append(f"- State: `{round_state}`")
    lines.append(f"- Generated at: `{generated_at}`")
    lines.append(f"- Forecast horizon (FH): `{fh}`")
    lines.append(f"- Run mode: `{run_mode}`")
    if lookup_date_override:
        lines.append(
            "- Override notice: "
            f"`lookup_date={lookup_date_override}` (backtest/evaluation mode, not strict production)"
        )
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

    if weighted_ensemble_df is not None and not weighted_ensemble_df.empty:
        lines.append("")
        lines.append("## Prior-Round Weighted Ensemble")
        lines.append("")
        if weights_source is not None:
            src_round = str(weights_source.get("source_round_id", ""))
            src_status = str(weights_source.get("weights_status", ""))
            if src_round:
                lines.append(f"- Source round: `{src_round}`")
            if src_status:
                lines.append(f"- Source status: `{src_status}`")
            lines.append("")

        header_we = ["Ticker", "Weighted FH", "Weights Used"]
        lines.append("| " + " | ".join(header_we) + " |")
        lines.append("|" + "|".join([":--" for _ in header_we]) + "|")
        for _, rec in weighted_ensemble_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rec.get("ticker", "")),
                        _fmt_number(rec.get("weighted_ensemble"), ndp=4),
                        _fmt_number(rec.get("weights_used_sum"), ndp=4),
                    ]
                )
                + " |"
            )

    if actuals_df is not None and not actuals_df.empty:
        lines.append("")
        lines.append("## +3 Actuals Ingestion")
        lines.append("")
        header2 = ["Ticker", "Expected", "Lookup", "Actual", "Status"]
        lines.append("| " + " | ".join(header2) + " |")
        lines.append("|" + "|".join([":--" for _ in header2]) + "|")
        for _, rec in actuals_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rec.get("ticker", "")),
                        str(rec.get("expected_actual_date", "")),
                        str(rec.get("lookup_actual_date", "")),
                        _fmt_number(rec.get("actual_close"), ndp=4),
                        str(rec.get("status", "")),
                    ]
                )
                + " |"
            )

    if score_summary_df is not None and not score_summary_df.empty:
        lines.append("")
        lines.append("## Partial Scoring")
        lines.append("")
        if score_stats is not None:
            lines.append(
                "- Coverage: "
                f"`{int(score_stats.get('scored_tickers', 0))}/{int(score_stats.get('total_tickers', 0))}` tickers "
                "with at least one scored model"
            )
            lines.append(
                "- Scored rows: "
                f"`{int(score_stats.get('scored_rows', 0))}/{int(score_stats.get('total_rows', 0))}`"
            )
            lines.append(
                "- Mean model coverage ratio: "
                f"`{_fmt_number(score_stats.get('model_coverage_avg', 0.0), ndp=3)}`"
            )
            lines.append("")

        header3 = [
            "Model",
            "Mean Accuracy",
            "Mean Assign",
            "Scored",
            "Expected",
            "Coverage",
        ]
        lines.append("| " + " | ".join(header3) + " |")
        lines.append("|" + "|".join([":--" for _ in header3]) + "|")
        for _, rec in score_summary_df.iterrows():
            cov_pct = 100.0 * _to_float_or_nan(rec.get("coverage_ratio"))
            cov_str = _fmt_number(cov_pct, ndp=1)
            cov_cell = f"{cov_str}%" if cov_str != "-" else "-"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rec.get("model", "")),
                        _fmt_number(rec.get("mean_accuracy_pct"), ndp=4),
                        _fmt_number(rec.get("mean_transformed_score"), ndp=4),
                        str(_to_int_or_zero(rec.get("scored_tickers"))),
                        str(_to_int_or_zero(rec.get("expected_tickers"))),
                        cov_cell,
                    ]
                )
                + " |"
            )

    if avr_summary_df is not None and not avr_summary_df.empty:
        lines.append("")
        lines.append("## AVR Memory (Scaffold)")
        lines.append("")
        if avr_stats is not None:
            lines.append(
                f"- History rows: `{_to_int_or_zero(avr_stats.get('history_rows', 0))}`"
            )
            lines.append(
                "- Models with history: "
                f"`{_to_int_or_zero(avr_stats.get('models_with_history', 0))}`"
            )
            lines.append("")

        header4 = [
            "Model",
            "Latest",
            "AVR4",
            "AVR6",
            "Rounds",
            "Next Weight",
        ]
        lines.append("| " + " | ".join(header4) + " |")
        lines.append("|" + "|".join([":--" for _ in header4]) + "|")
        for _, rec in avr_summary_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rec.get("model", "")),
                        _fmt_number(rec.get("latest_round_score"), ndp=4),
                        _fmt_number(rec.get("avr4"), ndp=4),
                        _fmt_number(rec.get("avr6"), ndp=4),
                        str(_to_int_or_zero(rec.get("rounds_count"))),
                        _fmt_number(rec.get("next_weight_suggested"), ndp=4),
                    ]
                )
                + " |"
            )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- This board is generated from persisted round artifacts under out/i_calc."
    )
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
        weighted_ensemble_df=None,
        weights_source=None,
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


def _dashboard_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{round_id}.md"


def _latest_dashboard_path() -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / "latest.md"


def _write_dashboard(round_id: str, content: str) -> Path:
    p = _dashboard_path(round_id)
    _write_nonempty_text(p, content)
    latest = _latest_dashboard_path()
    _write_nonempty_text(latest, p.read_text(encoding="utf-8"))
    return p


def _round_dir(round_id: str) -> Path:
    return (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / str(round_id)).resolve()


def _round_actuals_path(round_id: str) -> Path:
    return _round_dir(round_id) / "actuals_tplus3.csv"


def _global_actuals_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_ACTUALS_DIR / f"{round_id}_actuals.csv"


def _global_partial_scores_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR / f"{round_id}_partial_scores.csv"


def _global_model_summary_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR / f"{round_id}_model_summary.csv"


def _avr_history_path() -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_AVR_DIR / "avr_history.csv"


def _avr_summary_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_AVR_DIR / f"{round_id}_avr_summary.csv"


def _weights_path(round_id: str) -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR / f"{round_id}_next_weights.csv"


def _latest_weights_path() -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR / "latest_next_weights.csv"


def _latest_final_weights_path() -> Path:
    return paths.OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR / "latest_final_next_weights.csv"


def _round_sort_key(round_id: Any) -> Tuple[int, ...]:
    s = str(round_id)
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return (9999, 9999, 9999)
    if len(nums) == 1:
        return (nums[0], 0, 0)
    if len(nums) == 2:
        return (nums[0], nums[1], 0)
    return (nums[0], nums[1], nums[2])


def _load_avr_history() -> pd.DataFrame:
    p = _avr_history_path()
    if not p.exists():
        return pd.DataFrame(
            columns=[
                "round_id",
                "ticker",
                "model",
                "accuracy_pct",
                "transformed_score",
                "score_status",
                "transform_status",
                "updated_at",
            ]
        )
    try:
        df = pd.read_csv(p)
        required = [
            "round_id",
            "ticker",
            "model",
            "accuracy_pct",
            "transformed_score",
            "score_status",
            "transform_status",
            "updated_at",
        ]
        for c in required:
            if c not in df.columns:
                df[c] = (
                    ""
                    if c
                    in {
                        "round_id",
                        "ticker",
                        "model",
                        "score_status",
                        "transform_status",
                        "updated_at",
                    }
                    else NAN
                )
        return cast(pd.DataFrame, df[required].copy())
    except Exception as e:
        log.warning("Failed loading AVR history at %s: %s", p, e)
        return pd.DataFrame(
            columns=[
                "round_id",
                "ticker",
                "model",
                "accuracy_pct",
                "transformed_score",
                "score_status",
                "transform_status",
                "updated_at",
            ]
        )


def _upsert_avr_history(
    history_df: pd.DataFrame, scores_df: pd.DataFrame, *, round_id: str
) -> pd.DataFrame:
    h = cast(pd.DataFrame, history_df.copy())
    s = cast(
        pd.DataFrame,
        scores_df[
            [
                "round_id",
                "ticker",
                "model",
                "accuracy_pct",
                "transformed_score",
                "score_status",
                "transform_status",
            ]
        ].copy(),
    )
    s["round_id"] = str(round_id)
    s["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not h.empty:
        h = cast(pd.DataFrame, h[h["round_id"].astype(str) != str(round_id)].copy())

    out = cast(pd.DataFrame, pd.concat([h, s], ignore_index=True))
    out["accuracy_pct"] = pd.to_numeric(out["accuracy_pct"], errors="coerce")
    out["transformed_score"] = pd.to_numeric(out["transformed_score"], errors="coerce")
    out = cast(
        pd.DataFrame,
        out.drop_duplicates(subset=["round_id", "ticker", "model"], keep="last"),
    )
    return out


def _compute_avr_summary(
    history_df: pd.DataFrame, *, round_id: str
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    def _blank_summary() -> pd.DataFrame:
        rows = [
            {
                "model": m,
                "latest_round_score": NAN,
                "avr4": NAN,
                "avr6": NAN,
                "rounds_count": 0,
                "next_weight_suggested": NAN,
            }
            for m in MODEL_ORDER
        ]
        return pd.DataFrame(rows)

    if history_df.empty:
        empty = _blank_summary()
        return empty, {"history_rows": 0, "models_with_history": 0}

    h = cast(pd.DataFrame, history_df.copy())
    scored = cast(
        pd.DataFrame,
        h[
            (h["transform_status"] == "mapped") & (pd.notna(h["transformed_score"]))
        ].copy(),
    )
    if scored.empty:
        empty = _blank_summary()
        return empty, {"history_rows": int(len(history_df)), "models_with_history": 0}

    round_model = cast(
        pd.DataFrame,
        scored.groupby(["round_id", "model"], as_index=False).agg(
            round_score=("transformed_score", "mean"),
            scored_tickers=("ticker", "nunique"),
        ),
    )

    summary_rows: List[Dict[str, Any]] = []
    for model in MODEL_ORDER:
        mdf = cast(pd.DataFrame, round_model[round_model["model"] == model].copy())
        if mdf.empty:
            summary_rows.append(
                {
                    "model": model,
                    "latest_round_score": NAN,
                    "avr4": NAN,
                    "avr6": NAN,
                    "rounds_count": 0,
                    "next_weight_suggested": NAN,
                }
            )
            continue

        mdf["_rk"] = mdf["round_id"].map(_round_sort_key)
        mdf = cast(pd.DataFrame, mdf.sort_values(by=["_rk"]).reset_index(drop=True))

        vals = [float(v) for v in list(mdf["round_score"]) if _isfinite(v)]
        rounds_count = len(vals)
        latest_round_score = vals[-1] if vals else NAN
        avr4 = float(sum(vals[-4:]) / min(4, len(vals))) if vals else NAN
        avr6 = float(sum(vals[-6:]) / min(6, len(vals))) if vals else NAN

        next_weight = avr6 if _isfinite(avr6) else avr4
        summary_rows.append(
            {
                "model": model,
                "latest_round_score": latest_round_score,
                "avr4": avr4,
                "avr6": avr6,
                "rounds_count": rounds_count,
                "next_weight_suggested": next_weight,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df = cast(
        pd.DataFrame,
        summary_df.sort_values(
            by=["next_weight_suggested", "avr6", "avr4"],
            ascending=[False, False, False],
        ).reset_index(drop=True),
    )
    stats = {
        "history_rows": int(len(history_df)),
        "models_with_history": int(
            sum(1 for v in list(summary_df["rounds_count"]) if _to_int_or_zero(v) > 0)
        ),
        "current_round": str(round_id),
    }
    return summary_df, stats


def _export_next_weights(
    *,
    round_id: str,
    round_state: str,
    avr_summary_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Path, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for model in MODEL_ORDER:
        sub = cast(
            pd.DataFrame, avr_summary_df[avr_summary_df["model"] == model].copy()
        )
        raw = NAN
        avr4 = NAN
        avr6 = NAN
        rounds_count = 0
        if not sub.empty:
            rec = cast(pd.Series, sub.iloc[0])
            raw = _to_float_or_nan(rec.get("next_weight_suggested"))
            avr4 = _to_float_or_nan(rec.get("avr4"))
            avr6 = _to_float_or_nan(rec.get("avr6"))
            rounds_count = _to_int_or_zero(rec.get("rounds_count"))
        weight_raw = raw if _isfinite(raw) and raw > 0 else 0.0
        rows.append(
            {
                "round_id": str(round_id),
                "model": model,
                "weight_raw": float(weight_raw),
                "weight_norm": 0.0,
                "avr4": avr4,
                "avr6": avr6,
                "rounds_count": rounds_count,
            }
        )

    df = pd.DataFrame(rows)
    total_raw = float(cast(pd.Series, df["weight_raw"]).sum()) if not df.empty else 0.0
    if total_raw > 0:
        df["weight_norm"] = cast(pd.Series, df["weight_raw"]) / total_raw
    elif not df.empty:
        eq = 1.0 / float(len(df))
        df["weight_norm"] = eq

    df["rank"] = cast(pd.Series, df["weight_raw"]).rank(ascending=False, method="min")

    is_final = round_state in {ROUND_STATE_FINAL_TPLUS3, ROUND_STATE_REVISED}
    weights_status = "final" if is_final else "provisional"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["weights_status"] = weights_status
    df["source_round_state"] = str(round_state)
    df["generated_at"] = generated_at

    out_path = _weights_path(str(round_id))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cast(pd.DataFrame, df).to_csv(out_path, index=False)
    cast(pd.DataFrame, df).to_csv(_latest_weights_path(), index=False)
    if is_final:
        cast(pd.DataFrame, df).to_csv(_latest_final_weights_path(), index=False)

    stats = {
        "weights_status": weights_status,
        "models": int(len(df)),
        "total_raw": total_raw,
        "generated_at": generated_at,
        "weights_path": str(out_path),
    }
    return df, out_path, stats


def _load_prior_weights_for_round(
    round_id: str,
) -> Tuple[Dict[str, float], str, str, str]:
    """Load latest prior exported weights for consumption in draft rounds."""
    wdir = paths.OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR
    if not wdir.exists():
        return {}, "", "", ""

    current_key = _round_sort_key(round_id)
    candidates: List[Tuple[Tuple[int, ...], str, Path]] = []
    for p in wdir.glob("*_next_weights.csv"):
        stem = p.stem
        if not stem.endswith("_next_weights"):
            continue
        rid = stem[: -len("_next_weights")]
        key = _round_sort_key(rid)
        if key < current_key:
            candidates.append((key, rid, p))

    if not candidates:
        return {}, "", "", ""

    candidates.sort(key=lambda x: x[0])
    _, src_round, src_path = candidates[-1]

    try:
        df = pd.read_csv(src_path)
    except Exception:
        return {}, "", "", ""

    if "model" not in df.columns or "weight_norm" not in df.columns:
        return {}, "", "", ""

    weights_map: Dict[str, float] = {}
    for _, r in df.iterrows():
        m = str(r.get("model", ""))
        w = _to_float_or_nan(r.get("weight_norm"))
        if m and _isfinite(w) and w > 0:
            weights_map[m] = float(w)

    status = (
        str(df.get("weights_status").iloc[0])
        if "weights_status" in df.columns and not df.empty
        else ""
    )
    return weights_map, src_round, str(src_path), status


def _build_weighted_ensemble(
    dayn_df: pd.DataFrame, weights_map: Dict[str, float]
) -> pd.DataFrame:
    if dayn_df.empty or not weights_map:
        return pd.DataFrame(columns=["ticker", "weighted_ensemble", "weights_used_sum"])

    rows: List[Dict[str, Any]] = []
    for _, rec in dayn_df.iterrows():
        ticker = str(rec.get("ticker", ""))
        num = 0.0
        den = 0.0
        for model in MODEL_ORDER:
            w = float(weights_map.get(model, 0.0))
            if w <= 0:
                continue
            v = _to_float_or_nan(rec.get(model))
            if not _isfinite(v):
                continue
            num += float(v) * w
            den += w

        pred = float(num / den) if den > 0 else NAN
        rows.append(
            {
                "ticker": ticker,
                "weighted_ensemble": pred,
                "weights_used_sum": float(den),
            }
        )

    return pd.DataFrame(rows)


def _compute_partial_scores(
    *,
    round_id: str,
    forecasts_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    fh: int,
    mapping_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    fsub = cast(
        pd.DataFrame,
        forecasts_df[forecasts_df["fh_step"] == int(fh)].copy(),
    )
    if fsub.empty:
        empty_scores = pd.DataFrame(
            columns=[
                "round_id",
                "ticker",
                "model",
                "forecast_date",
                "expected_actual_date",
                "lookup_actual_date",
                "pred_value",
                "actual_close",
                "accuracy_pct",
                "transformed_score",
                "score_status",
                "transform_status",
            ]
        )
        empty_summary = pd.DataFrame(
            columns=[
                "model",
                "mean_accuracy_pct",
                "mean_transformed_score",
                "scored_tickers",
                "expected_tickers",
                "coverage_ratio",
            ]
        )
        return (
            empty_scores,
            empty_summary,
            {
                "scored_rows": 0,
                "total_rows": 0,
                "scored_tickers": 0,
                "total_tickers": 0,
                "model_coverage_avg": 0.0,
                "mapped_rows": 0,
            },
        )

    actuals_by_ticker: Dict[str, Dict[str, Any]] = {}
    for _, r in actuals_df.iterrows():
        t = str(r.get("ticker", ""))
        actuals_by_ticker[t] = dict(r)

    score_rows: List[Dict[str, Any]] = []
    for _, r in fsub.iterrows():
        ticker = str(r.get("ticker", ""))
        model = str(r.get("model", ""))
        forecast_date = str(r.get("forecast_date", ""))
        pred_value = _to_float_or_nan(r.get("pred_value"))
        forecast_status = str(r.get("status", ""))

        actual_rec = actuals_by_ticker.get(ticker, {})
        actual_status = str(actual_rec.get("status", "pending_actual"))
        expected_actual_date = str(actual_rec.get("expected_actual_date", ""))
        lookup_actual_date = str(
            actual_rec.get("lookup_actual_date", expected_actual_date)
        )
        actual_close = _to_float_or_nan(actual_rec.get("actual_close"))

        accuracy_pct = NAN
        transformed_score = NAN
        score_status = "pending_actual"
        transform_status = "pending_actual"

        if forecast_status != "ok":
            if forecast_status == "nan_pred":
                score_status = "nan_pred"
            else:
                score_status = "model_unavailable"
        else:
            if (
                actual_status == "ok"
                and _isfinite(actual_close)
                and abs(actual_close) > 0
            ):
                accuracy_pct = 100.0 - abs(
                    (actual_close - pred_value) / actual_close * 100.0
                )
                if _isfinite(accuracy_pct):
                    score_status = "scored"
                    transformed_score = _lookup_assign_value(accuracy_pct, mapping_df)
                    transform_status = (
                        "mapped" if _isfinite(transformed_score) else "nan_pred"
                    )
                else:
                    score_status = "nan_pred"
                    transform_status = "nan_pred"
            elif actual_status == "no_expected_date":
                score_status = "no_expected_date"
                transform_status = "no_expected_date"
            elif actual_status == "actual_missing":
                score_status = "actual_missing"
                transform_status = "actual_missing"
            else:
                score_status = "pending_actual"
                transform_status = "pending_actual"

        if score_status == "model_unavailable":
            transform_status = "model_unavailable"
        if score_status == "nan_pred":
            transform_status = "nan_pred"

        score_rows.append(
            {
                "round_id": str(round_id),
                "ticker": ticker,
                "model": model,
                "forecast_date": forecast_date,
                "expected_actual_date": expected_actual_date,
                "lookup_actual_date": lookup_actual_date,
                "pred_value": pred_value,
                "actual_close": actual_close,
                "accuracy_pct": accuracy_pct,
                "transformed_score": transformed_score,
                "score_status": score_status,
                "transform_status": transform_status,
            }
        )

    scores_df = pd.DataFrame(score_rows)
    expected_tickers = int(cast(pd.Series, fsub["ticker"]).nunique())

    summary_rows: List[Dict[str, Any]] = []
    for model in MODEL_ORDER:
        mdf = cast(pd.DataFrame, scores_df[scores_df["model"] == model].copy())
        scored = cast(pd.DataFrame, mdf[mdf["score_status"] == "scored"].copy())

        vals = [
            _to_float_or_nan(v)
            for v in list(scored["accuracy_pct"])
            if "accuracy_pct" in scored.columns
        ]
        vals_t = [
            _to_float_or_nan(v)
            for v in list(scored["transformed_score"])
            if "transformed_score" in scored.columns
        ]
        vals_f = [v for v in vals if _isfinite(v)]
        vals_t_f = [v for v in vals_t if _isfinite(v)]
        mean_acc = float(sum(vals_f) / len(vals_f)) if vals_f else NAN
        mean_tr = float(sum(vals_t_f) / len(vals_t_f)) if vals_t_f else NAN
        scored_tickers = (
            int(cast(pd.Series, scored["ticker"]).nunique()) if not scored.empty else 0
        )
        coverage_ratio = (
            float(scored_tickers / expected_tickers) if expected_tickers > 0 else 0.0
        )

        summary_rows.append(
            {
                "model": model,
                "mean_accuracy_pct": mean_acc,
                "mean_transformed_score": mean_tr,
                "scored_tickers": scored_tickers,
                "expected_tickers": expected_tickers,
                "coverage_ratio": coverage_ratio,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df = cast(
        pd.DataFrame,
        summary_df.sort_values(
            by=["mean_transformed_score", "coverage_ratio", "mean_accuracy_pct"],
            ascending=[False, False, False],
        ).reset_index(drop=True),
    )

    scored_rows = int((scores_df["score_status"] == "scored").sum())
    mapped_rows = int((scores_df["transform_status"] == "mapped").sum())
    total_rows = int(len(scores_df))
    scored_tickers = int(
        cast(
            pd.Series, scores_df[scores_df["score_status"] == "scored"]["ticker"]
        ).nunique()
    )
    total_tickers = int(cast(pd.Series, scores_df["ticker"]).nunique())
    cov_vals = [
        _to_float_or_nan(v)
        for v in list(summary_df["coverage_ratio"])
        if "coverage_ratio" in summary_df.columns
    ]
    cov_vals_f = [v for v in cov_vals if _isfinite(v)]
    model_cov_avg = float(sum(cov_vals_f) / len(cov_vals_f)) if cov_vals_f else 0.0

    stats = {
        "scored_rows": scored_rows,
        "total_rows": total_rows,
        "scored_tickers": scored_tickers,
        "total_tickers": total_tickers,
        "model_coverage_avg": model_cov_avg,
        "mapped_rows": mapped_rows,
    }
    return scores_df, summary_df, stats


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
                & (forecasts_df["status"] == "ok")
                & (forecasts_df["forecast_date"].notna())
                & (forecasts_df["forecast_date"].astype(str).str.strip() != "")
                & (forecasts_df["forecast_date"].astype(str).str.lower() != "nan")
            ][["forecast_date"]],
        )
        if sub.empty:
            out[t] = ""
            continue
        vc = cast(pd.Series, sub["forecast_date"].astype(str).value_counts())
        out[t] = str(vc.index[0]) if len(vc.index) > 0 else ""
    return out


def _normalize_yyyy_mm_dd(date_text: str) -> str:
    try:
        dt = pd.Timestamp(str(date_text))
        return str(dt.strftime("%Y-%m-%d"))
    except Exception:
        raise ValueError(f"Invalid date format: {date_text!r}. Expected yyyy-mm-dd.")


def _lookup_actual_close_for_date(
    runtime_ticker: str, lookup_date: str
) -> Tuple[float, str, str]:
    csv_path = resolve_raw_csv_path(runtime_ticker)
    df = fetch_data(runtime_ticker, csv_path=csv_path)
    if df is None or df.empty or "Close" not in df.columns:
        return NAN, "data_unavailable", str(csv_path)

    xdf = _to_datetime_index(df)
    if xdf.empty:
        return NAN, "data_unavailable", str(csv_path)

    idx_date = cast(pd.Series, xdf.index.to_series().dt.strftime("%Y-%m-%d"))
    mask = idx_date == str(lookup_date)
    if not bool(mask.any()):
        return NAN, "actual_missing", str(csv_path)

    matched = cast(pd.DataFrame, xdf.loc[mask.values].copy())
    if matched.empty:
        return NAN, "actual_missing", str(csv_path)

    close_v = _to_float_or_nan(cast(pd.Series, matched["Close"]).iloc[-1])
    if not _isfinite(close_v):
        return NAN, "actual_nan", str(csv_path)

    return float(close_v), "ok", str(csv_path)


def _actuals_changed(prev_df: pd.DataFrame, new_df: pd.DataFrame) -> bool:
    base_cols = [
        "ticker",
        "expected_actual_date",
        "lookup_actual_date",
        "status",
        "actual_close",
    ]
    p = cast(
        pd.DataFrame,
        prev_df.loc[:, [c for c in base_cols if c in prev_df.columns]].copy(),
    )
    n = cast(
        pd.DataFrame,
        new_df.loc[:, [c for c in base_cols if c in new_df.columns]].copy(),
    )
    if "actual_close" in p.columns:
        p["actual_close"] = pd.to_numeric(p["actual_close"], errors="coerce").round(8)
    if "actual_close" in n.columns:
        n["actual_close"] = pd.to_numeric(n["actual_close"], errors="coerce").round(8)
    p = cast(pd.DataFrame, p.sort_values(by=["ticker"]).reset_index(drop=True))
    n = cast(pd.DataFrame, n.sort_values(by=["ticker"]).reset_index(drop=True))
    return not p.equals(n)


def _finalize_override_policy(
    *,
    actual_lookup_date: Optional[str],
    allow_lookup_override: bool,
    override_reason: Optional[str],
    override_ticket: Optional[str],
    override_approver: Optional[str],
) -> Tuple[str, str, Dict[str, str]]:
    lookup_override = (
        _normalize_yyyy_mm_dd(actual_lookup_date)
        if actual_lookup_date is not None and str(actual_lookup_date).strip() != ""
        else ""
    )
    if lookup_override == "":
        return "", "strict_production", {"reason": "", "ticket": "", "approver": ""}

    if not allow_lookup_override:
        raise ValueError(
            "Override lookup date is blocked by production policy. "
            "Re-run with --allow-lookup-override and all required override ack fields."
        )

    ack = {
        "reason": str(override_reason or "").strip(),
        "ticket": str(override_ticket or "").strip(),
        "approver": str(override_approver or "").strip(),
    }
    missing = [k for k, v in ack.items() if v == ""]
    if missing:
        raise ValueError(
            "Override lookup date requires ack fields: override_reason, "
            "override_ticket, override_approver. Missing: " + ", ".join(missing)
        )

    return lookup_override, "lookup_override_test", ack


def run_tplus3_finalize_round(
    *,
    round_id: str,
    tickers: Optional[Iterable[str]] = None,
    actual_lookup_date: Optional[str] = None,
    allow_lookup_override: bool = False,
    override_reason: Optional[str] = None,
    override_ticket: Optional[str] = None,
    override_approver: Optional[str] = None,
) -> FinalizeArtifacts:
    """
    Ingest +3 actual values for a round and update round state.

    By default, strict matching is used (lookup date == expected +3 date).
    A fixed lookup date override is blocked by default and requires explicit
    break-glass acknowledgment fields.

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

    if (
        not context_json.exists()
        or not forecasts_csv.exists()
        or not draft_metrics_csv.exists()
    ):
        raise FileNotFoundError(
            f"Round artifacts missing for {round_id}. Expected files in {round_dir}."
        )

    context = json.loads(context_json.read_text(encoding="utf-8"))
    prev_state = str(context.get("round_state", ROUND_STATE_DRAFT_T0))
    fh_i = int(context.get("fh", DEFAULT_FH))
    lookup_override, run_mode, override_ack = _finalize_override_policy(
        actual_lookup_date=actual_lookup_date,
        allow_lookup_override=allow_lookup_override,
        override_reason=override_reason,
        override_ticket=override_ticket,
        override_approver=override_approver,
    )

    forecasts_df = pd.read_csv(forecasts_csv)
    ticker_list = _canonical_tickers(
        tickers or context.get("tickers", TICKER_ORDER_DEFAULT)
    )
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
                    "lookup_actual_date": "",
                    "actual_close": NAN,
                    "status": "no_expected_date",
                    "source_csv": "",
                }
            )
            continue

        lookup_date = lookup_override if lookup_override else expected_date
        actual_v, status, source_csv = _lookup_actual_close_for_date(
            runtime_t, lookup_date
        )
        rows.append(
            {
                "round_id": str(round_id),
                "ticker": t,
                "runtime_ticker": runtime_t,
                "expected_actual_date": expected_date,
                "lookup_actual_date": lookup_date,
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
        if _actuals_changed(
            cast(pd.DataFrame, prev_actuals_df), cast(pd.DataFrame, actuals_df)
        ):
            round_state = ROUND_STATE_REVISED

    round_actuals_csv = _round_actuals_path(round_id)
    global_actuals_csv = _global_actuals_path(round_id)
    partial_scores_csv = _global_partial_scores_path(round_id)
    model_summary_csv = _global_model_summary_path(round_id)
    round_actuals_csv.parent.mkdir(parents=True, exist_ok=True)
    global_actuals_csv.parent.mkdir(parents=True, exist_ok=True)
    partial_scores_csv.parent.mkdir(parents=True, exist_ok=True)
    cast(pd.DataFrame, actuals_df).to_csv(round_actuals_csv, index=False)
    cast(pd.DataFrame, actuals_df).to_csv(global_actuals_csv, index=False)

    mapping_df, mapping_path = _load_value_assign_table()

    scores_df, score_summary_df, score_stats = _compute_partial_scores(
        round_id=str(round_id),
        forecasts_df=cast(pd.DataFrame, forecasts_df),
        actuals_df=cast(pd.DataFrame, actuals_df),
        fh=fh_i,
        mapping_df=cast(pd.DataFrame, mapping_df),
    )
    cast(pd.DataFrame, scores_df).to_csv(partial_scores_csv, index=False)
    cast(pd.DataFrame, score_summary_df).to_csv(model_summary_csv, index=False)

    avr_history_csv = _avr_history_path()
    avr_summary_csv = _avr_summary_path(str(round_id))
    avr_history_csv.parent.mkdir(parents=True, exist_ok=True)
    avr_summary_csv.parent.mkdir(parents=True, exist_ok=True)

    avr_history_prev = _load_avr_history()
    avr_history_df = _upsert_avr_history(
        cast(pd.DataFrame, avr_history_prev),
        cast(pd.DataFrame, scores_df),
        round_id=str(round_id),
    )
    cast(pd.DataFrame, avr_history_df).to_csv(avr_history_csv, index=False)

    avr_summary_df, avr_stats = _compute_avr_summary(
        cast(pd.DataFrame, avr_history_df),
        round_id=str(round_id),
    )
    cast(pd.DataFrame, avr_summary_df).to_csv(avr_summary_csv, index=False)

    weights_df, next_weights_csv, weight_stats = _export_next_weights(
        round_id=str(round_id),
        round_state=round_state,
        avr_summary_df=cast(pd.DataFrame, avr_summary_df),
    )

    context["round_state"] = round_state
    context["run_mode"] = run_mode
    context["finalized_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context["actuals"] = {
        "ok_count": ok_count,
        "total": total,
        "strict_date_matching": bool(lookup_override == ""),
        "lookup_date_override": lookup_override,
        "run_mode": run_mode,
        "override_ack_required": bool(lookup_override != ""),
        "override_reason": str(override_ack.get("reason", "")),
        "override_ticket": str(override_ack.get("ticket", "")),
        "override_approver": str(override_ack.get("approver", "")),
        "actuals_csv": str(round_actuals_csv),
        "global_actuals_csv": str(global_actuals_csv),
    }
    context["scores"] = {
        "scored_rows": int(score_stats.get("scored_rows", 0)),
        "total_rows": int(score_stats.get("total_rows", 0)),
        "scored_tickers": int(score_stats.get("scored_tickers", 0)),
        "total_tickers": int(score_stats.get("total_tickers", 0)),
        "model_coverage_avg": float(score_stats.get("model_coverage_avg", 0.0)),
        "mapped_rows": int(score_stats.get("mapped_rows", 0)),
        "value_assign_table_path": str(mapping_path),
        "partial_scores_csv": str(partial_scores_csv),
        "model_summary_csv": str(model_summary_csv),
    }
    context["avr"] = {
        "history_rows": int(avr_stats.get("history_rows", 0)),
        "models_with_history": int(avr_stats.get("models_with_history", 0)),
        "avr_history_csv": str(avr_history_csv),
        "avr_summary_csv": str(avr_summary_csv),
    }
    context["weights"] = {
        "weights_status": str(weight_stats.get("weights_status", "")),
        "models": int(weight_stats.get("models", 0)),
        "total_raw": float(weight_stats.get("total_raw", 0.0)),
        "generated_at": str(weight_stats.get("generated_at", "")),
        "next_weights_csv": str(next_weights_csv),
    }
    scoring_cfg = cast(Dict[str, Any], context.get("scoring_config", {}))
    scoring_cfg["value_assign_table_path"] = str(mapping_path)
    context["scoring_config"] = scoring_cfg
    context_outputs = cast(Dict[str, Any], context.get("outputs", {}))
    context_outputs["actuals_csv"] = str(round_actuals_csv)
    context_outputs["global_actuals_csv"] = str(global_actuals_csv)
    context_outputs["partial_scores_csv"] = str(partial_scores_csv)
    context_outputs["model_summary_csv"] = str(model_summary_csv)
    context_outputs["avr_history_csv"] = str(avr_history_csv)
    context_outputs["avr_summary_csv"] = str(avr_summary_csv)
    context_outputs["next_weights_csv"] = str(next_weights_csv)
    context["outputs"] = context_outputs
    context_json.write_text(json.dumps(context, indent=2), encoding="utf-8")

    metrics_df = pd.read_csv(draft_metrics_csv)
    dayn_df = _build_dayn_matrix(cast(pd.DataFrame, forecasts_df), fh_step=fh_i)
    dashboard_md = _dashboard_path(str(round_id))
    md = _render_round_markdown(
        round_id=str(round_id),
        round_state=round_state,
        generated_at=str(context.get("generated_at", "")),
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
        actuals_df=cast(pd.DataFrame, actuals_df),
        score_summary_df=cast(pd.DataFrame, score_summary_df),
        score_stats=cast(Dict[str, Any], score_stats),
        avr_summary_df=cast(pd.DataFrame, avr_summary_df),
        avr_stats=cast(Dict[str, Any], avr_stats),
        weighted_ensemble_df=cast(Optional[pd.DataFrame], None),
        weights_source=cast(Optional[Dict[str, Any]], context.get("weights_applied")),
        run_mode=run_mode,
        lookup_date_override=lookup_override,
    )
    dashboard_md = _write_dashboard(str(round_id), md)

    return FinalizeArtifacts(
        round_id=str(round_id),
        round_state=round_state,
        run_mode=run_mode,
        lookup_date_override=lookup_override,
        ok_actuals=ok_count,
        total_actuals=total,
        scored_rows=int(score_stats.get("scored_rows", 0)),
        mapped_rows=int(score_stats.get("mapped_rows", 0)),
        total_score_rows=int(score_stats.get("total_rows", 0)),
        model_coverage_avg=float(score_stats.get("model_coverage_avg", 0.0)),
        actuals_csv=round_actuals_csv,
        partial_scores_csv=partial_scores_csv,
        model_summary_csv=model_summary_csv,
        avr_history_csv=avr_history_csv,
        avr_summary_csv=avr_summary_csv,
        next_weights_csv=next_weights_csv,
        context_json=context_json,
        dashboard_md=dashboard_md,
    )


def run_t0_draft_round(
    *,
    round_id: str,
    tickers: Optional[Iterable[str]] = None,
    fh: Optional[int] = None,
    history_mode: str = "live",
    as_of_date: Optional[str] = None,
) -> DraftArtifacts:
    """
    Build and persist a draft follow-up round (T0, no +3 actual values).
    """
    paths.ensure_directories()

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    ticker_list = _canonical_tickers(tickers)
    mode_text = str(history_mode or "live").strip().lower()
    if mode_text not in {"live", "replay"}:
        mode_text = "live"
    as_of_text = str(as_of_date or "").strip()
    if mode_text == "replay" and as_of_text == "":
        raise ValueError("as_of_date is required when history_mode='replay'")

    exo_config = _load_exo_config_optional(fh_i)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_rows: List[Dict[str, Any]] = []
    for logical_ticker in ticker_list:
        runtime_t = _runtime_ticker(logical_ticker)
        forecasts = _run_models_for_ticker(
            logical_ticker,
            fh=fh_i,
            exo_config=exo_config,
            history_mode=mode_text,
            as_of_date=(as_of_text or None),
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

    weights_map, src_round, src_path, src_status = _load_prior_weights_for_round(
        str(round_id)
    )
    weighted_ensemble_df = _build_weighted_ensemble(
        cast(pd.DataFrame, dayn_df),
        weights_map,
    )

    round_dir = _round_dir(round_id)
    round_dir.mkdir(parents=True, exist_ok=True)

    forecasts_csv = round_dir / "t0_forecasts.csv"
    draft_metrics_csv = round_dir / "t0_draft_metrics.csv"
    day3_matrix_csv = round_dir / f"t0_day{fh_i}_matrix.csv"
    weighted_ensemble_csv = round_dir / f"t0_day{fh_i}_weighted_ensemble.csv"
    context_json = round_dir / "round_context.json"
    dashboard_md = _dashboard_path(str(round_id))

    cast(pd.DataFrame, forecasts_df).to_csv(forecasts_csv, index=False)
    cast(pd.DataFrame, metrics_df).to_csv(draft_metrics_csv, index=False)
    cast(pd.DataFrame, dayn_df).to_csv(day3_matrix_csv, index=False)
    cast(pd.DataFrame, weighted_ensemble_df).to_csv(weighted_ensemble_csv, index=False)

    context: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "round_id": str(round_id),
        "round_state": ROUND_STATE_DRAFT_T0,
        "generated_at": generated_at,
        "fh": int(fh_i),
        "tickers": ticker_list,
        "models": list(MODEL_ORDER),
        "exo_config_path": str(paths.get_exo_config_path()),
        "scoring_config": {
            "value_assign_table_path": str(_resolve_value_assign_path()),
        },
        "weights_applied": {
            "source_round_id": src_round,
            "source_path": src_path,
            "weights_status": src_status,
            "models": int(len(weights_map)),
        },
        "history": {
            "mode": mode_text,
            "as_of_date": as_of_text,
        },
        "outputs": {
            "forecasts_csv": str(forecasts_csv),
            "draft_metrics_csv": str(draft_metrics_csv),
            "dayn_matrix_csv": str(day3_matrix_csv),
            "weighted_ensemble_csv": str(weighted_ensemble_csv),
            "dashboard_md": str(dashboard_md),
        },
    }
    context_json.write_text(json.dumps(context, indent=2), encoding="utf-8")

    md = _render_t0_markdown(
        round_id=round_id,
        generated_at=generated_at,
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
    )
    if not weighted_ensemble_df.empty:
        md = _render_round_markdown(
            round_id=round_id,
            round_state=ROUND_STATE_DRAFT_T0,
            generated_at=generated_at,
            fh=fh_i,
            dayn_df=cast(pd.DataFrame, dayn_df),
            metrics_df=cast(pd.DataFrame, metrics_df),
            actuals_df=None,
            weighted_ensemble_df=cast(pd.DataFrame, weighted_ensemble_df),
            weights_source={
                "source_round_id": src_round,
                "weights_status": src_status,
            },
        )
    dashboard_md = _write_dashboard(str(round_id), md)

    return DraftArtifacts(
        round_id=str(round_id),
        round_dir=round_dir,
        forecasts_csv=forecasts_csv,
        draft_metrics_csv=draft_metrics_csv,
        day3_matrix_csv=day3_matrix_csv,
        weighted_ensemble_csv=weighted_ensemble_csv,
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

    if (
        not context_json.exists()
        or not forecasts_csv.exists()
        or not draft_metrics_csv.exists()
    ):
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
    weighted_ensemble_df: Optional[pd.DataFrame] = None
    weights_source: Optional[Dict[str, Any]] = None

    weights_applied = context.get("weights_applied")
    if isinstance(weights_applied, dict):
        weights_source = cast(Dict[str, Any], weights_applied)

    outputs = cast(Dict[str, Any], context.get("outputs", {}))
    weighted_path = outputs.get("weighted_ensemble_csv")
    if weighted_path:
        pw = Path(str(weighted_path))
        if pw.exists():
            weighted_ensemble_df = pd.read_csv(pw)

    actuals_path = _round_actuals_path(round_id)
    actuals_df: Optional[pd.DataFrame] = None
    if actuals_path.exists():
        actuals_df = pd.read_csv(actuals_path)

    score_summary_df: Optional[pd.DataFrame] = None
    score_stats: Optional[Dict[str, Any]] = None
    avr_summary_df: Optional[pd.DataFrame] = None
    avr_stats: Optional[Dict[str, Any]] = None
    score_summary_path = outputs.get("model_summary_csv")
    if score_summary_path:
        p = Path(str(score_summary_path))
        if p.exists():
            score_summary_df = pd.read_csv(p)
    avr_summary_path = outputs.get("avr_summary_csv")
    if avr_summary_path:
        p2 = Path(str(avr_summary_path))
        if p2.exists():
            avr_summary_df = pd.read_csv(p2)
    if isinstance(context.get("scores"), dict):
        score_stats = cast(Dict[str, Any], context.get("scores"))
    if isinstance(context.get("avr"), dict):
        avr_stats = cast(Dict[str, Any], context.get("avr"))

    run_mode = str(context.get("run_mode", "strict_production"))
    lookup_date_override = ""
    actuals_meta = context.get("actuals")
    if isinstance(actuals_meta, dict):
        lookup_date_override = str(actuals_meta.get("lookup_date_override", ""))

    md = _render_round_markdown(
        round_id=str(round_id),
        round_state=round_state,
        generated_at=generated_at,
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
        actuals_df=cast(Optional[pd.DataFrame], actuals_df),
        score_summary_df=cast(Optional[pd.DataFrame], score_summary_df),
        score_stats=cast(Optional[Dict[str, Any]], score_stats),
        avr_summary_df=cast(Optional[pd.DataFrame], avr_summary_df),
        avr_stats=cast(Optional[Dict[str, Any]], avr_stats),
        weighted_ensemble_df=cast(Optional[pd.DataFrame], weighted_ensemble_df),
        weights_source=cast(Optional[Dict[str, Any]], weights_source),
        run_mode=run_mode,
        lookup_date_override=lookup_date_override,
    )
    dashboard_md = _write_dashboard(str(round_id), md)
    return dashboard_md
