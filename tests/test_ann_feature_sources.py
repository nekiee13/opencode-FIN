from __future__ import annotations

from pathlib import Path

from src.ui.services.ann_feature_sources import (
    ANN_EXCLUDED_MARKERS,
    PP_FEATURE_NAMES,
    SVL_HURST_FEATURE_NAMES,
    TDA_H1_FEATURE_NAMES,
    TI_FEATURE_NAMES,
    collect_ann_feature_records,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_ann_contract_excludes_marker_rows_and_requires_feature_sets() -> None:
    assert ANN_EXCLUDED_MARKERS == {"RD", "85220", "MICHO"}
    assert "RSI (14)" in TI_FEATURE_NAMES
    assert "ATR (14)" in TI_FEATURE_NAMES
    assert "Pivot Points(Classic)" in PP_FEATURE_NAMES
    assert SVL_HURST_FEATURE_NAMES == ("H20", "H60", "H120")
    assert TDA_H1_FEATURE_NAMES == (
        "H1_MaxPersistence",
        "H1_CountAbove_Thr",
        "H1_Entropy",
    )


def test_collect_ann_feature_records_reads_all_feature_families(tmp_path: Path) -> None:
    _write(
        tmp_path / "TI" / "GSPC.csv",
        "Date,RSI (14),ATR (14),BullBear Power\n2026-03-31,54.1,106.9,1.25\n",
    )
    _write(
        tmp_path / "PP" / "GSPC.csv",
        "Date,Pivot Points(Classic),R1(Classic)\n2026-03-31,6348.666,6373.333\n",
    )
    _write(
        tmp_path / "svl" / "SVL_METRICS_20260331.csv",
        "Ticker,Ticker_AsOf,H20,H60,H120\n"
        "AAPL,2026-03-31,0.37,0.51,0.50\n"
        "SPX,2026-03-31,0.49,0.50,0.52\n",
    )
    _write(
        tmp_path / "tda" / "TDA_METRICS_20260331.csv",
        "Global_AsOf,Ticker,Ticker_AsOf,H1_MaxPersistence,H1_CountAbove_Thr,H1_Entropy\n"
        "2026-03-31,SPX,2026-03-31,0.286,0,2.115\n",
    )

    out = collect_ann_feature_records(
        ti_dir=tmp_path / "TI",
        pp_dir=tmp_path / "PP",
        svl_dir=tmp_path / "svl",
        tda_dir=tmp_path / "tda",
    )

    assert out
    gspc_ti = [
        r
        for r in out
        if r["source_family"] == "ti"
        and r["ticker"] == "SPX"
        and r["feature_name"] == "RSI (14)"
    ]
    assert len(gspc_ti) == 1
    assert float(gspc_ti[0]["feature_value"]) == 54.1

    pp_rows = [
        r
        for r in out
        if r["source_family"] == "pivot"
        and r["feature_name"] == "Pivot Points(Classic)"
    ]
    assert len(pp_rows) == 1

    hurst_rows = [
        r
        for r in out
        if r["source_family"] == "hurst" and r["feature_name"] in {"H20", "H60", "H120"}
    ]
    assert len(hurst_rows) == 6

    tda_rows = [
        r
        for r in out
        if r["source_family"] == "tda_h1" and r["feature_name"] == "H1_Entropy"
    ]
    assert len(tda_rows) == 1
    assert float(tda_rows[0]["feature_value"]) == 2.115
