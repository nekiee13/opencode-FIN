from __future__ import annotations

import importlib.util
from pathlib import Path

from src.config import paths


def _load_llm_vg_store_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "src" / "followup_ml" / "llm_vg_store.py"
    spec = importlib.util.spec_from_file_location("followup_llm_vg_store", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


llm_vg_store = _load_llm_vg_store_module()


MODEL_TABLE_TEXT = """
|TICKER | TNX | DJI | SPX | VIX | QQQ | AAPL |
|:----|:----:|:----:|:----:|:----:|:----:|:----:|
| OAI-o5.2| 4.03-4.12<br>---<br>**4.07%** | 49666-49758<br>---<br>**49712** | 6854-6880<br>---<br>**6862** | 20.07-20.42<br>---<br>**20.31** | 600.70-605.15<br>---<br>**602.03** | 257.44-272.39<br>---<br>**259.68** |
| GROK-4.2 | 4.046-4.063<br>**4.055** | 49666-49758<br>**49690** | 6854-6880<br>**6865** | 20.07-20.42<br>**20.25** | 601-605<br>**602** | 264.65-268.84<br>**267** |
"""


MARKERS_TEXT = """
|TICKER | TNX | DJI | SPX | VIX | QQQ | AAPL |
|:----|:----:|:----:|:----:|:----:|:----:|:----:|
| Close<br>yahoo finance | 4.052 | 49533.19 | 6843.22 | 20.29 | 601.30 | 263.88 |
| Close<br>investing.com | 4.057 | 49533.19 | 6843.22 | 20.29 | 601.30 | 263.91 |
| Close<br>Anchor Mark   | 4.022 | 49499.41 | 6836.18 | 20.60 | 601.21 | 263.80 |
| +3-Day<br>CLOSE REAL   | 4.085 | 49625.97 | 6909.52 | 19.09 | 608.81 | 264.58 |
| RD | 4.00 | 49450 | 6803 | 21.18 | 597.3 | 266.4 |
| 85220 | 4.01 | 46485 | 6790 | 21.52 | 595.8 | 267.2 |
| MICH | 4.08 | 49622 | 6850 | 19.19 | 603.5 | 264.3 |
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_llm_model_table_extracts_actual_value() -> None:
    parsed = llm_vg_store.parse_llm_model_table(MODEL_TABLE_TEXT)
    assert parsed["tickers"] == ["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"]
    assert len(parsed["models"]) == 2

    first = parsed["models"][0]
    assert first["raw_model_label"] == "OAI-o5.2"
    assert abs(float(first["values"]["TNX"]) - 4.07) < 1e-9
    assert abs(float(first["values"]["DJI"]) - 49712.0) < 1e-9
    assert abs(float(first["values"]["AAPL"]) - 259.68) < 1e-9


def test_parse_markers_table_maps_anchor_mark_alias() -> None:
    parsed = llm_vg_store.parse_markers_table(MARKERS_TEXT)
    names = {row["marker_name"] for row in parsed["markers"]}
    assert llm_vg_store.MARKER_CLOSE_ANCHOR in names
    assert llm_vg_store.MARKER_CLOSE_REAL_TPLUS3 in names


def test_ingest_and_materialize_sparse_tail_with_alias_continuity(
    tmp_path, monkeypatch
) -> None:
    llm_db_path = tmp_path / "out" / "i_calc" / "LLM" / "LLM_VG_tables.sqlite"
    markers_db_path = tmp_path / "out" / "i_calc" / "Markers.sqlite"
    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"

    _write(mapping_path, "value,assign\n0,0\n95,95\n98,98\n99,99\n99.99,100\n")
    monkeypatch.setenv("FIN_LLM_VG_DB", str(llm_db_path))
    monkeypatch.setenv("FIN_MARKERS_DB", str(markers_db_path))
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    model_1 = tmp_path / "m1.md"
    model_2 = tmp_path / "m2.md"
    model_3 = tmp_path / "m3.md"
    mark_1 = tmp_path / "k1.md"
    mark_2 = tmp_path / "k2.md"
    mark_3 = tmp_path / "k3.md"

    _write(
        model_1,
        MODEL_TABLE_TEXT.replace("**4.07%**", "**100**").replace(
            "OAI-o5.2", "OAI-o4.0"
        ),
    )
    _write(
        model_2,
        MODEL_TABLE_TEXT.replace("**4.07%**", "**95**").replace("OAI-o5.2", "O 5.2"),
    )
    _write(
        model_3,
        MODEL_TABLE_TEXT.replace("**4.07%**", "**98**").replace("OAI-o5.2", "OAI-o5.4"),
    )

    marker_template = (
        MARKERS_TEXT.replace("4.085", "100")
        .replace("49625.97", "100")
        .replace("6909.52", "100")
        .replace("19.09", "100")
        .replace("608.81", "100")
        .replace("264.58", "100")
    )
    _write(mark_1, marker_template)
    _write(mark_2, marker_template)
    _write(mark_3, marker_template)

    llm_vg_store.ingest_llm_model_table_from_markdown(
        forecast_date="2026-02-03",
        round_id="26-1-01",
        markdown_path=model_1,
    )
    llm_vg_store.ingest_markers_from_markdown(
        forecast_date="2026-02-03",
        markdown_path=mark_1,
    )

    llm_vg_store.ingest_llm_model_table_from_markdown(
        forecast_date="2026-02-17",
        round_id="26-1-02",
        markdown_path=model_2,
    )
    llm_vg_store.ingest_markers_from_markdown(
        forecast_date="2026-02-17",
        markdown_path=mark_2,
    )

    llm_vg_store.ingest_llm_model_table_from_markdown(
        forecast_date="2026-03-03",
        round_id="26-1-03",
        markdown_path=model_3,
    )
    llm_vg_store.ingest_markers_from_markdown(
        forecast_date="2026-03-03",
        markdown_path=mark_3,
    )

    out = llm_vg_store.materialize_llm_vbg_for_date(
        "2026-03-03",
        memory_tail=4,
        bootstrap_enabled=True,
        bootstrap_score=99.0,
    )

    assert "OAI" in out["models"]
    assert out["violet"]["OAI"]["TNX"] is not None
    assert abs(float(out["violet"]["OAI"]["TNX"]) - 98.0) < 1e-9
    assert abs(float(out["blue"]["OAI"]["TNX"]) - 98.0) < 1e-9

    # history before 2026-03-03 has two observations for OAI/TNX: 100 and 95
    expected_green = (100.0 + 95.0 + 99.0 + 99.0) / 4.0
    got_green = out["green"]["OAI"]["TNX"]
    assert got_green is not None
    assert abs(float(got_green) - expected_green) < 1e-9

    meta = out["green_meta"]["OAI"]["TNX"]
    assert meta["real_rounds_used"] == 2
    assert meta["bootstrap_slots_used"] == 2


def test_unresolved_alias_is_reported(tmp_path, monkeypatch) -> None:
    llm_db_path = tmp_path / "LLM_VG_tables.sqlite"
    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n99,99\n")
    monkeypatch.setenv("FIN_LLM_VG_DB", str(llm_db_path))
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    table_path = tmp_path / "unknown.md"
    text = MODEL_TABLE_TEXT.replace("OAI-o5.2", "Unknown LLM Zeta")
    _write(table_path, text)

    result = llm_vg_store.ingest_llm_model_table_from_markdown(
        forecast_date="2026-04-01",
        round_id="26-2-01",
        markdown_path=table_path,
    )
    assert "Unknown LLM Zeta" in result["unresolved_model_labels"]
