from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.ui.services.ann_feature_store import (
    initialize_ann_feature_store,
    upsert_ann_feature_records,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_ann_store(path: Path) -> None:
    initialize_ann_feature_store(path)
    records: list[dict[str, object]] = []
    for ticker in ("TNX", "DJI"):
        for d, val in (
            ("2026-03-31", 10.0),
            ("2026-04-01", 11.0),
            ("2026-04-02", 12.0),
        ):
            records.append(
                {
                    "as_of_date": d,
                    "ticker": ticker,
                    "feature_name": "RSI (14)",
                    "feature_value": val,
                    "source_family": "ti",
                    "source_file": "/tmp/TI/seed.csv",
                    "value_status": "present",
                }
            )
    upsert_ann_feature_records(
        store_path=path,
        records=records,
        source_batch="B1",
    )


def _seed_rounds(rounds_dir: Path) -> None:
    for d, tnx_p, dji_p in (
        ("20260331", 4.20, 46000.0),
        ("20260401", 4.30, 46100.0),
        ("20260402", 4.10, 45900.0),
    ):
        _write(
            rounds_dir / f"anchor-{d}" / "t0_day1_weighted_ensemble.csv",
            "ticker,weighted_ensemble,weights_used_sum\n"
            f"TNX,{tnx_p},1.0\n"
            f"DJI,{dji_p},1.0\n",
        )


def _seed_raw_tickers(raw_dir: Path) -> None:
    _write(
        raw_dir / "TNX_data.csv",
        "Date,Open,High,Low,Close,Volume\n"
        "2026-03-31,4.1,4.2,4.0,4.11,100\n"
        "2026-04-01,4.2,4.3,4.1,4.21,100\n"
        "2026-04-02,4.0,4.2,3.9,4.00,100\n",
    )
    _write(
        raw_dir / "DJI_data.csv",
        "Date,Open,High,Low,Close,Volume\n"
        "2026-03-31,46000,46100,45900,46050,100\n"
        "2026-04-01,46100,46200,46000,46120,100\n"
        "2026-04-02,45900,46000,45800,45950,100\n",
    )


def test_ann_tune_writes_per_ticker_target_matrix(tmp_path: Path) -> None:
    store_path = tmp_path / "ann_input_features.sqlite"
    rounds_dir = tmp_path / "rounds"
    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out"

    _seed_ann_store(store_path)
    _seed_rounds(rounds_dir)
    _seed_raw_tickers(raw_dir)

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/ann_tune.py",
            "--store-path",
            str(store_path),
            "--rounds-dir",
            str(rounds_dir),
            "--raw-tickers-dir",
            str(raw_dir),
            "--tickers",
            "TNX",
            "DJI",
            "--target-modes",
            "magnitude",
            "sgn",
            "--max-trials",
            "1",
            "--output-dir",
            str(out_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    marker = "[ann_tune] output_dir="
    line = next((x for x in proc.stdout.splitlines() if x.startswith(marker)), "")
    assert line
    run_dir = Path(line.split("=", 1)[1].strip())
    matrix_path = run_dir / "best_config_matrix.json"
    assert matrix_path.exists()

    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert "TNX" in payload
    assert "DJI" in payload
    assert "magnitude" in payload["TNX"]
    assert "sgn" in payload["TNX"]
