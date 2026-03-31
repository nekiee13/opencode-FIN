from __future__ import annotations

import ast
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"Expected class {name!r} in src/ui/gui.py")


def _class_constant_value(cls: ast.ClassDef, name: str) -> str | None:
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        return node.value.value
                    return None
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    return node.value.value
                return None
    return None


def test_stock_analysis_app_all_tickers_label_is_class_constant() -> None:
    source_path = _repo_root() / "src" / "ui" / "gui.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    app_class = _find_class(tree, "StockAnalysisApp")
    label = _class_constant_value(app_class, "ALL_TICKERS_LABEL")

    assert label == "ALL_TICKERS"
