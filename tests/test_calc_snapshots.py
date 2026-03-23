from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.config import paths
from src.utils import calc_snapshots as snap


def _mk_model_df(
    pred_col: str,
    pred_vals: list[float],
    lower_col: Optional[str] = None,
    lower_vals: Optional[list[float]] = None,
    upper_col: Optional[str] = None,
    upper_vals: Optional[list[float]] = None,
) -> pd.DataFrame:
    idx = pd.date_range("2026-02-18", periods=len(pred_vals), freq="B")
    data: Dict[str, list[float]] = {pred_col: pred_vals}
    if lower_col and lower_vals is not None:
        data[lower_col] = lower_vals
    if upper_col and upper_vals is not None:
        data[upper_col] = upper_vals
    return pd.DataFrame(data, index=idx)


def test_persist_ti_snapshot_upsert_and_chronological_sort(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_dir = tmp_path / "out" / "i_calc" / "TI"
    monkeypatch.setattr(paths, "OUT_I_CALC_TI_DIR", out_dir)

    indicators = pd.Series(
        {
            "Close": 49533.19,
            "MA50": 48987.7752,
            "MA200": 46086.4172,
            "RSI (14)": 52.8117,
            "Stochastic %K": 51.2348,
            "ATR (14)": 614.9027,
            "ADX (14)": 12.2849,
            "CCI (14)": -5.1169,
            "Williams %R": -47.7176,
            "Ultimate Oscillator": 48.36,
            "ROC (10)": 0.5934,
            "BullBear Power": -213.1365,
        }
    )

    pivot_data = {"Classic": {"Pivot": 49443.0867}}

    snap.persist_ti_snapshot(
        ticker="DJI",
        asof_date="2026-02-17",
        latest_indicators=indicators,
        pivot_data=pivot_data,
    )
    snap.persist_ti_snapshot(
        ticker="DJI",
        asof_date="2026-02-15",
        latest_indicators=indicators,
        pivot_data=pivot_data,
    )

    indicators_overwrite = indicators.copy()
    indicators_overwrite["Close"] = 50000.0
    snap.persist_ti_snapshot(
        ticker="DJI",
        asof_date="2026-02-17",
        latest_indicators=indicators_overwrite,
        pivot_data=pivot_data,
    )

    out_path = out_dir / "DJI.csv"
    assert out_path.exists()

    df = pd.read_csv(out_path)
    assert list(df.columns) == snap.TI_COLUMNS
    assert list(df["Date"]) == ["2026-02-15", "2026-02-17"]

    row = df.loc[df["Date"] == "2026-02-17"].iloc[0]
    assert float(row["Current Value"]) == 50000.0


def test_persist_pp_snapshot_upsert_and_missing_levels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_dir = tmp_path / "out" / "i_calc" / "PP"
    monkeypatch.setattr(paths, "OUT_I_CALC_PP_DIR", out_dir)

    pivot_data = {
        "Classic": {
            "S3": 48123.827,
            "S2": 48783.457,
            "S1": 49142.193,
            "Pivot": 49443.087,
            "R1": 49801.823,
            "R2": 50102.717,
            "R3": 50762.347,
        },
        "Fibonacci": {
            "S3": 48783.457,
            "S2": 49035.435,
            "S1": 49191.108,
            "Pivot": 49443.087,
            "R1": 49695.065,
            "R2": 49850.738,
            "R3": 50102.717,
        },
        "Camarilla": {
            "S3": 49319.532,
            "S2": 49379.998,
            "S1": 49440.464,
            "Pivot": 49443.087,
            "R1": 49561.396,
            "R2": 49621.862,
            "R3": 49682.328,
        },
        "Woodie's": {
            "S2": 48810.137,
            "S1": 49195.555,
            "Pivot": 49469.768,
            "R1": 49855.185,
            "R2": 50129.398,
        },
        "DeMark's": {
            "S1": 48962.825,
            "Pivot": 49353.402,
            "R1": 49622.455,
        },
    }

    snap.persist_pp_snapshot(
        ticker="DJI", asof_date="2026-02-17", pivot_data=pivot_data
    )
    snap.persist_pp_snapshot(
        ticker="DJI", asof_date="2026-02-16", pivot_data=pivot_data
    )

    pivot_data_overwrite = dict(pivot_data)
    pivot_data_overwrite["Classic"] = dict(pivot_data["Classic"])
    pivot_data_overwrite["Classic"]["Pivot"] = 50000.0
    snap.persist_pp_snapshot(
        ticker="DJI",
        asof_date="2026-02-17",
        pivot_data=pivot_data_overwrite,
    )

    out_path = out_dir / "DJI.csv"
    assert out_path.exists()

    df = pd.read_csv(out_path)
    assert list(df["Date"]) == ["2026-02-16", "2026-02-17"]
    assert str(df.loc[df["Date"] == "2026-02-17", "S3(Woodie's)"].iloc[0]) == "-"

    row = df.loc[df["Date"] == "2026-02-17"].iloc[0]
    assert float(row["Pivot Points(Classic)"]) == 50000.0


def test_persist_ml_snapshots_upsert_and_markdown_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_dir = tmp_path / "out" / "i_calc" / "ML"
    monkeypatch.setattr(paths, "OUT_I_CALC_ML_DIR", out_dir)

    model_results_tnx = {
        "TorchForecast": _mk_model_df("TorchForecast_Pred", [4.1, 4.2, 4.3]),
        "ARIMAX": _mk_model_df(
            "ARIMAX_Pred",
            [4.0, 4.1, 4.2],
            "ARIMAX_Lower",
            [3.8, 3.9, 4.0],
            "ARIMAX_Upper",
            [4.2, 4.3, 4.4],
        ),
        "PCE": None,
        "LSTM": _mk_model_df(
            "LSTM_Pred",
            [4.0, 4.05, 4.1],
            "LSTM_Lower",
            [3.7, 3.8, 3.9],
            "LSTM_Upper",
            [4.3, 4.4, 4.5],
        ),
        "GARCH": _mk_model_df("GARCH_Pred", [4.1, 4.15, 4.2]),
        "VAR": _mk_model_df("VAR_Pred", [4.0, 4.05, 4.1]),
        "RW": _mk_model_df("RW_Pred", [4.0, 4.1, 4.2]),
        "ETS": _mk_model_df("ETS_Pred", [4.0, 4.05, 4.1]),
        "DYNAMIX": _mk_model_df("DYNAMIX_Pred", [4.04, 4.05, 4.06]),
        "DYNAMIX_NONSTATIONARY": _mk_model_df("DYNAMIX_Pred", [4.01, 4.02, 4.03]),
    }

    model_results_dji = {
        "TorchForecast": _mk_model_df("TorchForecast_Pred", [49700, 49750, 49800]),
        "ARIMAX": _mk_model_df(
            "ARIMAX_Pred",
            [49600, 49700, 49800],
            "ARIMAX_Lower",
            [49200, 49300, 49400],
            "ARIMAX_Upper",
            [50000, 50100, 50200],
        ),
        "PCE": None,
        "LSTM": None,
        "GARCH": _mk_model_df("GARCH_Pred", [49650, 49700, 49750]),
        "VAR": _mk_model_df("VAR_Pred", [49500, 49550, 49600]),
        "RW": _mk_model_df("RW_Pred", [49520, 49580, 49620]),
        "ETS": _mk_model_df("ETS_Pred", [49510, 49570, 49610]),
        "DYNAMIX": _mk_model_df("DYNAMIX_Pred", [49500.1, 49510.1, 49520.1]),
        "DYNAMIX_NONSTATIONARY": _mk_model_df(
            "DYNAMIX_Pred", [49490.1, 49500.1, 49510.1]
        ),
    }

    csv_path, md_path = snap.persist_ml_snapshots(
        ticker="TNX",
        asof_date="2026-02-17",
        model_results=model_results_tnx,
        ticker_order=("TNX", "DJI", "GSPC", "VIX", "QQQ", "AAPL"),
    )
    assert csv_path.exists()
    assert md_path.exists()

    snap.persist_ml_snapshots(
        ticker="DJI",
        asof_date="2026-02-17",
        model_results=model_results_dji,
        ticker_order=("TNX", "DJI", "GSPC", "VIX", "QQQ", "AAPL"),
    )

    model_results_tnx_overwrite = dict(model_results_tnx)
    model_results_tnx_overwrite["TorchForecast"] = _mk_model_df(
        "TorchForecast_Pred", [4.5, 4.6, 4.7]
    )
    snap.persist_ml_snapshots(
        ticker="TNX",
        asof_date="2026-02-17",
        model_results=model_results_tnx_overwrite,
        ticker_order=("TNX", "DJI", "GSPC", "VIX", "QQQ", "AAPL"),
    )

    csv_df = pd.read_csv(csv_path)
    assert list(csv_df.columns) == snap.ML_MAIN_COLUMNS
    assert list(csv_df["Ticker"]) == ["TNX", "DJI"]
    assert float(csv_df.loc[csv_df["Ticker"] == "TNX", "Torch"].iloc[0]) == 4.7

    md = md_path.read_text(encoding="utf-8")
    assert "| TNX |" in md
    assert "| DJI |" in md
    assert "<br> ~" in md
