from __future__ import annotations

import json
from pathlib import Path

from src.ui.services.ann_info import build_ann_guides_markdown, load_ann_info


def _seed_setup(path: Path, *, ticker: str, split_policy: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ticker": ticker,
                "active": True,
                "training": {
                    "split_policy": split_policy,
                    "learning_rate": 0.001,
                },
                "model": {
                    "type": "MLP",
                },
            }
        ),
        encoding="utf-8",
    )


def test_load_ann_info_scopes_all_tickers(tmp_path: Path) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    ann_dir = out_i_calc_dir / "ANN"
    _seed_setup(ann_dir / "TNX.setup.json", ticker="TNX", split_policy="walk_forward")
    _seed_setup(ann_dir / "DJI.setup.json", ticker="DJI", split_policy="single_split")

    tune_dir = ann_dir / "tuning" / "tune_20260409-010101"
    tune_dir.mkdir(parents=True, exist_ok=True)
    (tune_dir / "best_config_matrix.json").write_text(
        json.dumps(
            {
                "TNX": {
                    "magnitude": {"status": "healthy"},
                    "sgn": {"status": "fails_baseline"},
                },
                "DJI": {
                    "magnitude": {"status": "insufficient_data"},
                    "sgn": {"status": "healthy"},
                },
            }
        ),
        encoding="utf-8",
    )

    profile_path = out_i_calc_dir / "ann" / "feature_profiles" / "pruned_inputs.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        '{"selected_features": ["ti::RSI (14)__lag0"]}', encoding="utf-8"
    )

    payload = load_ann_info(
        selected_ticker="ALL",
        tickers=["TNX", "DJI"],
        out_i_calc_dir=out_i_calc_dir,
        store_summary={"exists": True, "store_path": "dummy"},
    )

    assert payload["scope"]["selected_tickers"] == ["TNX", "DJI"]
    assert payload["profile"]["is_active"] is True
    assert payload["latest_tune"]["run_id"] == "tune_20260409-010101"
    assert payload["tickers"]["TNX"]["setup_exists"] is True
    assert payload["tickers"]["TNX"]["tune_matrix"]["magnitude"]["status"] == "healthy"
    assert payload["tickers"]["DJI"]["setup_exists"] is True


def test_load_ann_info_scopes_single_ticker(tmp_path: Path) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    ann_dir = out_i_calc_dir / "ANN"
    _seed_setup(ann_dir / "TNX.setup.json", ticker="TNX", split_policy="walk_forward")
    _seed_setup(ann_dir / "DJI.setup.json", ticker="DJI", split_policy="single_split")

    payload = load_ann_info(
        selected_ticker="TNX",
        tickers=["TNX", "DJI"],
        out_i_calc_dir=out_i_calc_dir,
        store_summary={"exists": False, "store_path": "missing"},
    )

    assert payload["scope"]["selected_tickers"] == ["TNX"]
    assert list(payload["tickers"].keys()) == ["TNX"]
    assert payload["tickers"]["TNX"]["setup_exists"] is True


def test_build_ann_guides_markdown_covers_requested_topics() -> None:
    guides = build_ann_guides_markdown()

    assert "Run ANN Feature Ingest" in guides
    assert "Run ANN Marker Ingest (Legacy)" in guides
    assert "Window Length" in guides
    assert "Lag Depth" in guides
    assert "Tune Max Trials" in guides
    assert "Prune Keep Ratio" in guides
    assert "Prune Inputs" in guides
    assert "Run ANN Train" in guides
    assert "Run ANN Tune" in guides
