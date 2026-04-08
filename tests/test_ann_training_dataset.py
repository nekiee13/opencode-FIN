from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ann.config import ANNTrainingConfig
from src.ann.dataset import build_training_dataset
from src.ui.services.ann_feature_store import initialize_ann_feature_store


def _seed_store(path: Path) -> None:
    initialize_ann_feature_store(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            INSERT INTO ann_ti_inputs(
                as_of_date, ticker, feature_name, feature_value, value_status,
                source_file, source_batch, loaded_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-31",
                "TNX",
                "RSI (14)",
                52.0,
                "present",
                "seed.csv",
                "B1",
                "2026-03-31T00:00:00Z",
                "2026-03-31T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO ann_ti_inputs(
                as_of_date, ticker, feature_name, feature_value, value_status,
                source_file, source_batch, loaded_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-01",
                "TNX",
                "RSI (14)",
                55.0,
                "present",
                "seed.csv",
                "B1",
                "2026-04-01T00:00:00Z",
                "2026-04-01T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_ticker_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-03-31,4.1,4.2,4.0,4.11,100\n"
        "2026-04-01,4.2,4.3,4.1,4.21,100\n"
        "2026-04-02,4.3,4.4,4.2,4.33,100\n",
        encoding="utf-8",
    )


def test_build_training_dataset_creates_lagged_features(tmp_path: Path) -> None:
    store_path = tmp_path / "ann_input_features.sqlite"
    _seed_store(store_path)
    raw_dir = tmp_path / "raw"
    _seed_ticker_csv(raw_dir / "TNX_data.csv")

    cfg = ANNTrainingConfig(window_length=1, lag_depth=1)
    ds = build_training_dataset(
        store_path=store_path,
        raw_tickers_dir=raw_dir,
        tickers=["TNX"],
        config=cfg,
    )

    assert ds.feature_columns
    assert any(name.endswith("__lag1") for name in ds.feature_columns)
    assert ds.X.shape[0] >= 1
    assert ds.y.shape[0] == ds.X.shape[0]
