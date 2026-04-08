from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd

from src.ann.config import ANNTrainingConfig
from src.config import paths

FAMILY_TABLES: tuple[tuple[str, str], ...] = (
    ("ti", "ann_ti_inputs"),
    ("pivot", "ann_pivot_inputs"),
    ("hurst", "ann_hurst_inputs"),
    ("tda_h1", "ann_tda_h1_inputs"),
)


@dataclass(frozen=True)
class TrainingDataset:
    X: np.ndarray
    y: np.ndarray
    feature_columns: list[str]
    frame: pd.DataFrame


def _ticker_candidates(ticker: str) -> list[str]:
    t = str(ticker).strip().upper()
    if t == "SPX":
        return ["SPX", "GSPC"]
    return [t]


def _load_feature_rows(store_path: Path) -> pd.DataFrame:
    if not store_path.exists():
        return pd.DataFrame(
            columns=["as_of_date", "ticker", "feature_name", "feature_value"]
        )

    conn = sqlite3.connect(str(store_path))
    try:
        chunks: list[pd.DataFrame] = []
        for family, table in FAMILY_TABLES:
            try:
                q = (
                    "SELECT as_of_date, ticker, feature_name, feature_value "
                    f"FROM {table} WHERE value_status = 'present'"
                )
                df = pd.read_sql_query(q, conn)
            except Exception:
                continue
            if df.empty:
                continue
            df["feature_name"] = (
                family + "::" + df["feature_name"].astype(str).str.strip()
            )
            chunks.append(df)
    finally:
        conn.close()

    if not chunks:
        return pd.DataFrame(
            columns=["as_of_date", "ticker", "feature_name", "feature_value"]
        )
    out = pd.concat(chunks, ignore_index=True)
    out["as_of_date"] = pd.to_datetime(out["as_of_date"], errors="coerce")
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    out["feature_value"] = pd.to_numeric(out["feature_value"], errors="coerce")
    return out.dropna(subset=["as_of_date"]).copy()


def _load_close_series(raw_tickers_dir: Path, ticker: str) -> pd.DataFrame:
    last_exc: Exception | None = None
    for candidate in _ticker_candidates(ticker):
        csv_path = raw_tickers_dir / f"{candidate}_data.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path)
            if "Date" not in df.columns or "Close" not in df.columns:
                continue
            out = df[["Date", "Close"]].copy()
            out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
            out["Close"] = pd.to_numeric(out["Close"], errors="coerce")
            out = out.loc[out["Date"].notna() & out["Close"].notna()].copy()
            out = out.sort_values("Date").reset_index(drop=True)
            out["ticker"] = candidate if candidate != "GSPC" else "SPX"
            return out
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    return pd.DataFrame(columns=["Date", "Close", "ticker"])


def _parse_anchor_date_from_round_name(name: str) -> pd.Timestamp | None:
    text = str(name or "").strip()
    m = re.search(r"(\d{8})$", text)
    if not m:
        return None
    try:
        parsed = pd.to_datetime(m.group(1), format="%Y%m%d", errors="coerce")
        if isinstance(parsed, pd.Timestamp):
            return parsed
        return None
    except Exception:
        return None


def _load_weighted_ensemble_rows(rounds_dir: Path) -> pd.DataFrame:
    if not rounds_dir.exists():
        return pd.DataFrame(columns=["Date", "ticker", "P"])

    chunks: list[pd.DataFrame] = []
    for csv_path in sorted(rounds_dir.glob("*/t0_day1_weighted_ensemble.csv")):
        date_value = _parse_anchor_date_from_round_name(csv_path.parent.name)
        if date_value is None:
            continue
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        if "ticker" not in df.columns or "weighted_ensemble" not in df.columns:
            continue
        one = df[["ticker", "weighted_ensemble"]].copy()
        one["ticker"] = one["ticker"].astype(str).str.upper().str.strip()
        p_values = pd.to_numeric(one["weighted_ensemble"], errors="coerce")
        one = one.assign(P=p_values, Date=date_value)
        one = one.loc[one["P"].notna()].copy()
        if not one.empty:
            chunks.append(one[["Date", "ticker", "P"]])

    if not chunks:
        return pd.DataFrame(columns=["Date", "ticker", "P"])
    out = pd.concat(chunks, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out = out.dropna(subset=["Date"]).copy()
    return out


def _apply_lags(
    frame: pd.DataFrame, base_cols: list[str], max_lag: int
) -> pd.DataFrame:
    out = frame.copy()
    lagged_map: dict[str, pd.Series] = {}
    for col in base_cols:
        for lag in range(max_lag + 1):
            lagged_map[f"{col}__lag{lag}"] = out[col].shift(lag)
    if not lagged_map:
        return out
    lagged_df = pd.DataFrame(lagged_map)
    return pd.concat([out, lagged_df], axis=1)


def build_training_dataset(
    *,
    store_path: Path,
    raw_tickers_dir: Path,
    tickers: list[str],
    config: ANNTrainingConfig,
    train_end_date: str | None = None,
    rounds_dir: Path | None = None,
    target_mode: str = "magnitude",
) -> TrainingDataset:
    mode = str(target_mode or "magnitude").strip().lower()
    if mode not in {"magnitude", "sgn"}:
        raise ValueError("target_mode must be 'magnitude' or 'sgn'")

    feature_rows = _load_feature_rows(store_path)
    effective_rounds_dir = (
        Path(rounds_dir).resolve()
        if rounds_dir is not None
        else paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR.resolve()
    )
    ensemble_rows = _load_weighted_ensemble_rows(effective_rounds_dir)
    if feature_rows.empty:
        return TrainingDataset(
            X=np.zeros((0, 0), dtype=float),
            y=np.zeros((0,), dtype=float),
            feature_columns=[],
            frame=pd.DataFrame(),
        )

    feature_wide = feature_rows.pivot_table(
        index=["as_of_date", "ticker"],
        columns="feature_name",
        values="feature_value",
        aggfunc="last",
    ).reset_index()
    feature_wide = feature_wide.rename(columns={"as_of_date": "Date"})

    ticker_frames: list[pd.DataFrame] = []
    selected = [str(x).strip().upper() for x in tickers if str(x).strip()]
    end_ts: pd.Timestamp | None = None
    if train_end_date is not None:
        text = str(train_end_date).strip()
        if text:
            parsed = pd.to_datetime(text, errors="coerce")
            if isinstance(parsed, pd.Timestamp):
                end_ts = parsed
    for ticker in selected:
        close_df = _load_close_series(raw_tickers_dir, ticker)
        if close_df.empty:
            continue
        t_features = feature_wide.loc[feature_wide["ticker"] == ticker].copy()
        if t_features.empty:
            continue
        t_ensemble = ensemble_rows.loc[ensemble_rows["ticker"] == ticker].copy()
        if t_ensemble.empty:
            continue
        merged = t_features.merge(close_df, on=["Date", "ticker"], how="inner")
        merged = merged.merge(t_ensemble, on=["Date", "ticker"], how="inner")
        if merged.empty:
            continue
        if end_ts is not None:
            merged = merged.loc[merged["Date"] <= end_ts].copy()
            if merged.empty:
                continue
        merged = merged.sort_values("Date").reset_index(drop=True)
        h = int(config.forecast_horizon)
        future_close = merged["Close"].shift(-h)
        if mode == "magnitude":
            target = (merged["Close"] - merged["P"]).abs()
        else:
            trend = np.where(
                merged["P"] > merged["Close"],
                1.0,
                np.where(merged["P"] < merged["Close"], -1.0, 0.0),
            )
            realized = np.where(
                future_close > merged["Close"],
                1.0,
                np.where(future_close < merged["Close"], -1.0, 0.0),
            )
            target = np.where((trend != 0.0) & (trend == realized), 1.0, -1.0)
            target = pd.Series(target, index=merged.index, dtype=float)
            target = target.where(pd.notna(future_close), np.nan)
        merged["target"] = target
        ticker_frames.append(merged)

    if not ticker_frames:
        return TrainingDataset(
            X=np.zeros((0, 0), dtype=float),
            y=np.zeros((0,), dtype=float),
            feature_columns=[],
            frame=pd.DataFrame(),
        )

    by_ticker: list[pd.DataFrame] = []
    for item in ticker_frames:
        reserved = {"Date", "ticker", "Close", "P", "target"}
        base_features = [c for c in item.columns if c not in reserved]
        lagged = _apply_lags(
            item, base_features, max(config.lag_depth, config.window_length - 1)
        )
        by_ticker.append(lagged)

    full = pd.concat(by_ticker, ignore_index=True)
    full = full.sort_values(["ticker", "Date"]).reset_index(drop=True)
    reserved = {"Date", "ticker", "Close", "P", "target"}
    feature_cols = [c for c in full.columns if c not in reserved and "__lag" in c]
    full[feature_cols] = full[feature_cols].fillna(0.0)
    full = full.dropna(subset=["target"]).copy()
    if full.empty:
        return TrainingDataset(
            X=np.zeros((0, len(feature_cols)), dtype=float),
            y=np.zeros((0,), dtype=float),
            feature_columns=feature_cols,
            frame=full,
        )

    X = full[feature_cols].to_numpy(dtype=float)
    y = full["target"].to_numpy(dtype=float)
    return TrainingDataset(X=X, y=y, feature_columns=feature_cols, frame=full)
