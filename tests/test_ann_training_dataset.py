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
        conn.execute(
            """
            INSERT INTO ann_ti_inputs(
                as_of_date, ticker, feature_name, feature_value, value_status,
                source_file, source_batch, loaded_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-02",
                "TNX",
                "RSI (14)",
                49.0,
                "present",
                "seed.csv",
                "B1",
                "2026-04-02T00:00:00Z",
                "2026-04-02T00:00:00Z",
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


def _seed_weighted_ensemble(
    rounds_dir: Path,
    *,
    anchor_date: str,
    ticker: str,
    weighted_ensemble: float,
) -> None:
    round_dir = rounds_dir / f"anchor-{anchor_date.replace('-', '')}"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "t0_day1_weighted_ensemble.csv").write_text(
        "ticker,weighted_ensemble,weights_used_sum\n"
        f"{ticker},{weighted_ensemble},1.0\n",
        encoding="utf-8",
    )


def test_build_training_dataset_creates_lagged_features(tmp_path: Path) -> None:
    store_path = tmp_path / "ann_input_features.sqlite"
    _seed_store(store_path)
    raw_dir = tmp_path / "raw"
    _seed_ticker_csv(raw_dir / "TNX_data.csv")
    rounds_dir = tmp_path / "rounds"
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-03-31",
        ticker="TNX",
        weighted_ensemble=4.20,
    )
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-04-01",
        ticker="TNX",
        weighted_ensemble=4.10,
    )

    cfg = ANNTrainingConfig(window_length=1, lag_depth=1)
    ds = build_training_dataset(
        store_path=store_path,
        raw_tickers_dir=raw_dir,
        tickers=["TNX"],
        config=cfg,
        rounds_dir=rounds_dir,
    )

    assert ds.feature_columns
    assert any(name.endswith("__lag1") for name in ds.feature_columns)
    assert ds.X.shape[0] >= 1
    assert ds.y.shape[0] == ds.X.shape[0]


def test_build_training_dataset_respects_train_end_date(tmp_path: Path) -> None:
    store_path = tmp_path / "ann_input_features.sqlite"
    _seed_store(store_path)
    raw_dir = tmp_path / "raw"
    _seed_ticker_csv(raw_dir / "TNX_data.csv")
    rounds_dir = tmp_path / "rounds"
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-03-31",
        ticker="TNX",
        weighted_ensemble=4.20,
    )
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-04-01",
        ticker="TNX",
        weighted_ensemble=4.10,
    )

    cfg = ANNTrainingConfig(window_length=1, lag_depth=1)
    ds = build_training_dataset(
        store_path=store_path,
        raw_tickers_dir=raw_dir,
        tickers=["TNX"],
        config=cfg,
        train_end_date="2026-04-01",
        rounds_dir=rounds_dir,
    )

    assert not ds.frame.empty
    assert str(ds.frame["Date"].max().strftime("%Y-%m-%d")) <= "2026-04-01"


def test_build_training_dataset_supports_sgn_target_mode(tmp_path: Path) -> None:
    store_path = tmp_path / "ann_input_features.sqlite"
    _seed_store(store_path)
    raw_dir = tmp_path / "raw"
    (raw_dir / "TNX_data.csv").parent.mkdir(parents=True, exist_ok=True)
    (raw_dir / "TNX_data.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-03-31,4.1,4.2,4.0,4.00,100\n"
        "2026-04-01,4.2,4.3,4.1,4.20,100\n"
        "2026-04-02,4.0,4.2,3.9,3.80,100\n",
        encoding="utf-8",
    )
    rounds_dir = tmp_path / "rounds"
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-03-31",
        ticker="TNX",
        weighted_ensemble=4.30,
    )
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-04-01",
        ticker="TNX",
        weighted_ensemble=4.40,
    )
    _seed_weighted_ensemble(
        rounds_dir,
        anchor_date="2026-04-02",
        ticker="TNX",
        weighted_ensemble=3.60,
    )

    cfg = ANNTrainingConfig(window_length=1, lag_depth=1)
    magnitude = build_training_dataset(
        store_path=store_path,
        raw_tickers_dir=raw_dir,
        tickers=["TNX"],
        config=cfg,
        rounds_dir=rounds_dir,
        target_mode="magnitude",
    )
    sgn = build_training_dataset(
        store_path=store_path,
        raw_tickers_dir=raw_dir,
        tickers=["TNX"],
        config=cfg,
        rounds_dir=rounds_dir,
        target_mode="sgn",
    )

    assert magnitude.y.shape[0] >= sgn.y.shape[0]
    assert any(abs(float(x) - 0.3) < 1e-9 for x in magnitude.y.tolist())
    assert set(float(x) for x in sgn.y.tolist()).issubset({-1.0, 0.0, 1.0})
    assert 1.0 in [float(x) for x in sgn.y.tolist()]
    assert -1.0 in [float(x) for x in sgn.y.tolist()]
