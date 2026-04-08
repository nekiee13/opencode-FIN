from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.ui.services.ann_feature_store import load_ann_feature_store_summary


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_source_dirs(base: Path) -> tuple[Path, Path, Path, Path]:
    ti_dir = base / "TI"
    pp_dir = base / "PP"
    svl_dir = base / "svl"
    tda_dir = base / "tda"

    _write(
        ti_dir / "GSPC.csv",
        "Date,RSI (14),ATR (14),BullBear Power\n2026-03-31,54.1,106.9,1.25\n",
    )
    _write(
        pp_dir / "GSPC.csv",
        "Date,Pivot Points(Classic),R1(Classic)\n2026-03-31,6348.666,6373.333\n",
    )
    _write(
        svl_dir / "SVL_METRICS_20260331.csv",
        "Ticker,Ticker_AsOf,H20,H60,H120\nSPX,2026-03-31,0.49,0.50,0.52\n",
    )
    _write(
        tda_dir / "TDA_METRICS_20260331.csv",
        "Global_AsOf,Ticker,Ticker_AsOf,H1_MaxPersistence,H1_CountAbove_Thr,H1_Entropy\n"
        "2026-03-31,SPX,2026-03-31,0.286,0,2.115\n",
    )
    return ti_dir, pp_dir, svl_dir, tda_dir


def test_ann_feature_stores_ingest_cli_writes_family_tables(tmp_path: Path) -> None:
    ti_dir, pp_dir, svl_dir, tda_dir = _seed_source_dirs(tmp_path)
    store_path = tmp_path / "ann_input_features.sqlite"
    script_path = Path("scripts") / "ann_feature_stores_ingest.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--ti-dir",
            str(ti_dir),
            "--pp-dir",
            str(pp_dir),
            "--svl-dir",
            str(svl_dir),
            "--tda-dir",
            str(tda_dir),
            "--store-path",
            str(store_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    summary = load_ann_feature_store_summary(store_path)
    assert summary["families"]["ti"]["rows"] == 3
    assert summary["families"]["pivot"]["rows"] == 2
    assert summary["families"]["hurst"]["rows"] == 3
    assert summary["families"]["tda_h1"]["rows"] == 3


def test_ann_feature_stores_ingest_cli_force_mode(tmp_path: Path) -> None:
    ti_dir, pp_dir, svl_dir, tda_dir = _seed_source_dirs(tmp_path)
    store_path = tmp_path / "ann_input_features.sqlite"
    script_path = Path("scripts") / "ann_feature_stores_ingest.py"

    base_cmd = [
        sys.executable,
        str(script_path),
        "--ti-dir",
        str(ti_dir),
        "--pp-dir",
        str(pp_dir),
        "--svl-dir",
        str(svl_dir),
        "--tda-dir",
        str(tda_dir),
        "--store-path",
        str(store_path),
    ]

    first = subprocess.run(
        base_cmd,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    second = subprocess.run(
        [*base_cmd, "--force"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0
    assert second.returncode == 0
