from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_tda_exporter_handles_per_ticker_load_exception(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts import tda_export

    def _fake_fetch_data(ticker: str, csv_path=None):  # type: ignore[no-untyped-def]
        if ticker == "BAD":
            raise ValueError("simulated csv parse failure")
        idx = pd.bdate_range("2025-10-01", periods=90, freq="B")
        return pd.DataFrame(
            {"Close": pd.Series(range(100, 190), index=idx, dtype=float)}
        )

    monkeypatch.setattr(tda_export, "fetch_data", _fake_fetch_data)

    out_dir = tmp_path / "out_tda"
    raw_dir = tmp_path / "raw"

    paths = tda_export.export_tda_artifacts(
        tickers=["OK", "BAD"],
        out_dir=out_dir,
        raw_dir=raw_dir,
        write_metrics_csv=True,
        write_prompt_header=False,
    )

    assert paths.context_md.exists()
    assert paths.metrics_csv is not None and paths.metrics_csv.exists()

    md = paths.context_md.read_text(encoding="utf-8")
    assert "OK" in md
    assert "BAD" in md

    df = pd.read_csv(paths.metrics_csv)
    tickers = set(df["Ticker"].astype(str).tolist())
    assert "OK" in tickers
    assert "BAD" in tickers
