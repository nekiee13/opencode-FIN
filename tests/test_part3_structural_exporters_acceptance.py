# ------------------------
# tests/test_part3_structural_exporters_acceptance.py
# ------------------------
# tests/test_part3_structural_exporters_acceptance.py
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path
from typing import List

import pandas as pd
import pytest

pytestmark = pytest.mark.cpi


def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(12):
        if (cur / "scripts").is_dir() and (cur / "src").is_dir():
            return cur
        cur = cur.parent
    raise RuntimeError("Repository root not found (expected 'scripts/' and 'src/' directories).")


def _write_ohlcv_csv(path: Path, dates: List[str], close0: float = 100.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    close = float(close0)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for d in dates:
            open_ = close * 0.99
            high = close * 1.01
            low = close * 0.98
            vol = 1_000_000
            w.writerow([d, open_, high, low, close, vol])
            close *= 1.002


def _run_py(script: Path, args: List[str], *, cwd: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(script)] + args
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _glob_one(dirpath: Path, pattern: str) -> Path:
    matches = list(dirpath.glob(pattern))
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one match for {pattern} in {dirpath}, found {len(matches)}")
    return matches[0]


def _asof_tag_from_filename(path: Path) -> str:
    m = re.search(r"_(\d{8})\.", path.name)
    if not m:
        raise AssertionError(f"ASOF tag not found in filename: {path.name}")
    return m.group(1)


def test_svl_export_writes_artifacts_and_uses_global_min_asof(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__).resolve())
    script = repo_root / "scripts" / "svl_export.py"

    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out_svl"

    d1 = ["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10"]
    d2 = ["2026-01-06", "2026-01-07", "2026-01-08"]

    _write_ohlcv_csv(raw_dir / "AAA_data.csv", d1, close0=100.0)
    _write_ohlcv_csv(raw_dir / "BBB_data.csv", d2, close0=200.0)

    _run_py(
        script,
        [
            "--csv-dir", str(raw_dir),
            "--out-dir", str(out_dir),
            "--tickers", "AAA", "BBB",
            "--write-metrics",
            "--write-prompt-header",
        ],
        cwd=repo_root,
    )

    md = _glob_one(out_dir, "SVL_CONTEXT_*.md")
    metrics = _glob_one(out_dir, "SVL_METRICS_*.csv")
    hdr = _glob_one(out_dir, "SVL_PROMPT_HEADER_*.txt")

    assert _asof_tag_from_filename(md) == "20260108"
    assert _asof_tag_from_filename(metrics) == "20260108"
    assert _asof_tag_from_filename(hdr) == "20260108"

    md_text = _read_text(md)
    assert "STRUCTURAL_CONTEXT" in md_text
    assert "AAA" in md_text
    assert "BBB" in md_text

    dfm = pd.read_csv(metrics)
    required_cols = {"Ticker", "Ticker_AsOf", "H20", "H60", "H120", "Regime_current", "Trend10D"}
    assert required_cols.issubset(set(dfm.columns))
    assert set(dfm["Ticker"].astype(str).tolist()) == {"AAA", "BBB"}


def test_tda_export_writes_artifacts_under_missing_dependency(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__).resolve())
    script = repo_root / "scripts" / "tda_export.py"

    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out_tda"

    dates = pd.date_range("2025-10-01", periods=90, freq="D").strftime("%Y-%m-%d").tolist()
    _write_ohlcv_csv(raw_dir / "AAA_data.csv", dates, close0=100.0)

    tickers = ["AAA", "MISSING_TICKER"]

    _run_py(
        script,
        [
            "--tickers", *tickers,
            "--raw-dir", str(raw_dir),
            "--out-dir", str(out_dir),
            "--write-metrics",
            "--write-prompt-header",
        ],
        cwd=repo_root,
    )

    md = _glob_one(out_dir, "TDA_CONTEXT_*.md")
    metrics = _glob_one(out_dir, "TDA_METRICS_*.csv")
    _glob_one(out_dir, "TDA_PROMPT_HEADER_*.txt")

    md_text = _read_text(md)
    assert "TDA_CONTEXT" in md_text
    assert "AAA" in md_text
    assert "MISSING_TICKER" in md_text

    dfm = pd.read_csv(metrics)

    required_cols = {
        "Global_AsOf",
        "Ticker",
        "Ticker_AsOf",
        "State",
        "window_len",
        "embed_m",
        "embed_tau",
        "persist_thr",
        "H1_MaxPersistence",
        "H1_CountAbove_Thr",
        "H1_Entropy",
    }
    missing_cols = sorted(required_cols.difference(set(dfm.columns)))
    assert not missing_cols, f"Missing CPI-required columns: {missing_cols}"

    assert set(int(v) for v in dfm["window_len"].tolist()) == {60}
    assert set(int(v) for v in dfm["embed_m"].tolist()) == {3}
    assert set(int(v) for v in dfm["embed_tau"].tolist()) == {1}
    assert set(round(float(v), 6) for v in dfm["persist_thr"].tolist()) == {0.5}

    tickers_out = set(str(v) for v in dfm["Ticker"].tolist())
    assert "MISSING_TICKER" in tickers_out

    allowed_states: set[str] = {"OK", "MISSING_DEP", "INSUFFICIENT_DATA", "DEGENERATE", "ERROR"}
    observed_states: set[str] = set(str(v) for v in dfm["State"].tolist())

    non_cpi_states = sorted(observed_states.difference(allowed_states))
    assert observed_states.issubset(allowed_states), f"Non-CPI states observed: {non_cpi_states}"


def test_tda_export_global_asof_is_min_across_tickers(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__).resolve())
    script = repo_root / "scripts" / "tda_export.py"

    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "out_tda"

    d1 = pd.date_range("2025-10-01", periods=90, freq="D").strftime("%Y-%m-%d").tolist()
    d2 = pd.date_range("2025-10-01", periods=70, freq="D").strftime("%Y-%m-%d").tolist()

    _write_ohlcv_csv(raw_dir / "AAA_data.csv", d1, close0=100.0)
    _write_ohlcv_csv(raw_dir / "BBB_data.csv", d2, close0=200.0)

    _run_py(
        script,
        [
            "--tickers", "AAA", "BBB",
            "--raw-dir", str(raw_dir),
            "--out-dir", str(out_dir),
        ],
        cwd=repo_root,
    )

    md = _glob_one(out_dir, "TDA_CONTEXT_*.md")

    expected = pd.to_datetime(d2[-1]).strftime("%Y%m%d")
    assert _asof_tag_from_filename(md) == expected
