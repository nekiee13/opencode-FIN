from __future__ import annotations

from src.ui.services import ann_ingredients_pipeline


def test_build_ann_ingredient_commands_orders_stages_and_replay_args() -> None:
    commands = ann_ingredients_pipeline.build_ann_ingredient_commands(
        selected_date="2025-08-19",
        tickers=["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"],
        ingest_after_each_date=True,
    )

    stages = [c.stage for c in commands]
    assert stages == [
        "ti_pp_backfill",
        "svl_export",
        "tda_export",
        "make_fh3_table",
        "ann_feature_ingest",
    ]

    svl_cmd = commands[1].command
    assert "--history-mode" in svl_cmd
    assert "replay" in svl_cmd
    assert "--as-of-date" in svl_cmd
    assert "2025-08-19" in svl_cmd
    assert "--map-json" in svl_cmd

    tda_cmd = commands[2].command
    assert "--map" in tda_cmd
    assert "SPX=GSPC" in tda_cmd

    fh3_cmd = commands[3].command
    assert "--tickers" in fh3_cmd
    for ticker in ["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"]:
        assert ticker in fh3_cmd


def test_build_ann_ingredient_commands_supports_end_only_ingest() -> None:
    commands = ann_ingredients_pipeline.build_ann_ingredient_commands(
        selected_date="2025-08-19",
        tickers=["TNX", "DJI"],
        ingest_after_each_date=False,
    )
    assert [c.stage for c in commands] == [
        "ti_pp_backfill",
        "svl_export",
        "tda_export",
        "make_fh3_table",
    ]


def test_resolve_dates_uses_sidebar_source_and_sorts_ascending(monkeypatch) -> None:
    monkeypatch.setattr(
        ann_ingredients_pipeline,
        "load_sidebar_date_options",
        lambda: ["2026-03-31", "2025-08-19", "2026-03-24", "2025-08-19"],
    )
    out = ann_ingredients_pipeline.resolve_processing_dates(
        start_date="2025-08-19",
        end_date="2026-03-31",
        explicit_dates=None,
    )
    assert out == ["2025-08-19", "2026-03-24", "2026-03-31"]
