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


def _run_models_for_ticker(
    logical_ticker: str,
    *,
    fh: int,
    exo_config: Optional[Any],
) -> Dict[str, Optional[pd.DataFrame]]:
    runtime_ticker = _runtime_ticker(logical_ticker)
    out: Dict[str, Optional[pd.DataFrame]] = {k: None for k in MODEL_ORDER}

    try:
        out["Torch"] = models_api.run_external_torch_forecasting(runtime_ticker)
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
        out["DYNAMIX"] = models_api.predict_dynamix(
            enriched, ticker=runtime_ticker, fh=fh, fit_nonstationary=False
        )
    except Exception as e:
        log.warning("DYNAMIX failed for %s: %s", logical_ticker, e)

    try:
        arimax_df, _, _ = models_api.predict_arima(
            enriched, ticker=runtime_ticker, exo_config=exo_config
        )
        out["ARIMAX"] = arimax_df
    except Exception as e:
        log.warning("ARIMAX failed for %s: %s", logical_ticker, e)

    try:
        out["PCE"] = models_api.predict_pce_narx(
            enriched, ticker=runtime_ticker, exo_config=exo_config
        )
    except Exception as e:
        log.warning("PCE failed for %s: %s", logical_ticker, e)

    try:
        out["LSTM"] = models_api.predict_lstm(
            enriched, ticker=runtime_ticker, exo_config=exo_config
        )
    except Exception as e:
        log.warning("LSTM failed for %s: %s", logical_ticker, e)

    try:
        out["GARCH"] = models_api.predict_arch_model(
            enriched, ticker=runtime_ticker, exo_config=exo_config
        )
    except Exception as e:
        log.warning("GARCH failed for %s: %s", logical_ticker, e)

    try:
        out["VAR"] = models_api.predict_var(enriched)
    except Exception as e:
        log.warning("VAR failed for %s: %s", logical_ticker, e)

    try:
        out["RW"] = models_api.predict_random_walk(enriched)
    except Exception as e:
        log.warning("RW failed for %s: %s", logical_ticker, e)

    try:
        out["ETS"] = models_api.predict_exp_smoothing(enriched)
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


def _render_t0_markdown(
    *,
    round_id: str,
    generated_at: str,
    fh: int,
    dayn_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
) -> str:
    lines: List[str] = []
    lines.append(f"# Follow-up ML Board - {round_id}")
    lines.append("")
    lines.append(f"- State: `{ROUND_STATE_DRAFT_T0}`")
    lines.append(f"- Generated at: `{generated_at}`")
    lines.append(f"- Forecast horizon (FH): `{fh}`")
    lines.append("- Accuracy/scoring fields: `Pending +3 actual values`")
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

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This is a draft dashboard at T0; no post-event accuracy is computed yet.")
    lines.append("- Final scoring should be computed after +3-day actual values are available.")
    lines.append("")
    return "\n".join(lines)


def _round_dir(round_id: str) -> Path:
    return (paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / str(round_id)).resolve()


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
    dashboard_md.write_text(md, encoding="utf-8")

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

    forecasts_df = pd.read_csv(forecasts_csv)
    metrics_df = pd.read_csv(draft_metrics_csv)
    dayn_df = _build_dayn_matrix(cast(pd.DataFrame, forecasts_df), fh_step=fh_i)

    md = _render_t0_markdown(
        round_id=str(round_id),
        generated_at=generated_at,
        fh=fh_i,
        dayn_df=cast(pd.DataFrame, dayn_df),
        metrics_df=cast(pd.DataFrame, metrics_df),
    )
    dashboard_md = paths.OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR / f"{round_id}_draft.md"
    dashboard_md.parent.mkdir(parents=True, exist_ok=True)
    dashboard_md.write_text(md, encoding="utf-8")
    return dashboard_md
