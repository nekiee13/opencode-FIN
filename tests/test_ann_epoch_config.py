from __future__ import annotations

from pathlib import Path

from src.ui.services.ann_epoch_config import (
    epochs_for_ticker_mode,
    load_epoch_rows,
    save_epoch_rows,
)


def test_load_epoch_rows_bootstraps_defaults(tmp_path: Path) -> None:
    path = tmp_path / "epoch.csv"
    rows, errors, out_path = load_epoch_rows(path=path)
    assert out_path == path.resolve()
    assert errors == []
    assert len(rows) == 6
    assert rows[0]["Ticker"] == "TNX"
    assert rows[0]["SGN"] == 200
    assert rows[0]["Magnitude"] == 600


def test_save_epoch_rows_rejects_missing_tickers(tmp_path: Path) -> None:
    rows = [{"Ticker": "TNX", "SGN": 200, "Magnitude": 600}]
    saved, errors, _ = save_epoch_rows(rows, path=tmp_path / "epoch.csv")
    assert saved == []
    assert errors
    assert any("Missing epoch row for DJI" in x for x in errors)


def test_epochs_for_ticker_mode_reads_mode_specific_values() -> None:
    rows = [
        {"Ticker": "TNX", "SGN": 150, "Magnitude": 700},
        {"Ticker": "DJI", "SGN": 200, "Magnitude": 1200},
    ]
    assert epochs_for_ticker_mode(rows, ticker="TNX", mode="sgn", fallback=1) == 150
    assert (
        epochs_for_ticker_mode(rows, ticker="TNX", mode="magnitude", fallback=1) == 700
    )
    assert epochs_for_ticker_mode(rows, ticker="QQQ", mode="sgn", fallback=222) == 222
