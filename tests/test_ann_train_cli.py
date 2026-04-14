from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ann_train_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ann_train.py"
    spec = importlib.util.spec_from_file_location("ann_train_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ann_train_parse_args_defaults_to_all_modes_and_epochs_csv() -> None:
    mod = _load_ann_train_module()
    args = mod.parse_args([])
    assert args.target_mode == "all"
    normalized = str(args.epochs_csv).replace("\\", "/")
    assert normalized.endswith("out/i_calc/ANN/epoch.csv")


def test_ann_train_selected_modes_expands_all() -> None:
    mod = _load_ann_train_module()
    assert mod._selected_modes("all") == ["sgn", "magnitude"]
    assert mod._selected_modes("sgn") == ["sgn"]
    assert mod._selected_modes("magnitude") == ["magnitude"]
