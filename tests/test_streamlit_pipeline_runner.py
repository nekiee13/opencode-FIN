from __future__ import annotations

import sys
from pathlib import Path

from src.ui.services.pipeline_runner import (
    CommandSpec,
    TICKER_ORDER,
    build_pipeline_commands,
    run_command,
)


def test_build_pipeline_commands_single_ticker_replay_mode() -> None:
    commands = build_pipeline_commands(
        selected_date="2026-03-24",
        selected_ticker="TNX",
    )
    assert len(commands) == 5
    core = commands[:3]
    for spec in core:
        joined = " ".join(spec.command)
        assert "--history-mode" in joined
        assert "replay" in joined
        assert "--as-of-date" in joined
        assert "2026-03-24" in joined


def test_build_pipeline_commands_all_tickers_in_sequence() -> None:
    commands = build_pipeline_commands(
        selected_date="2026-03-24",
        selected_ticker="ALL",
    )
    core = [x for x in commands if x.category == "core"]
    assert len(core) == (len(TICKER_ORDER) * 2) + 1
    assert core[0].ticker == TICKER_ORDER[0]
    fh3 = [x for x in core if x.stage == "make_fh3_table"]
    assert len(fh3) == 1
    assert fh3[0].ticker == "ALL"
    assert fh3[0].command.count("--tickers") == 1
    for ticker in TICKER_ORDER:
        assert ticker in fh3[0].command

    ann = [x for x in commands if x.category == "store" and "ann" in x.stage]
    assert len(ann) == 1
    assert ann[0].command[-1].endswith("ann_feature_stores_ingest.py")


def test_run_command_sets_utf8_pythonioencoding(tmp_path: Path) -> None:
    script = tmp_path / "check_env.py"
    script.write_text(
        "\n".join(
            [
                "import os, sys",
                "value = os.getenv('PYTHONIOENCODING', '')",
                "print(value)",
                "sys.exit(0 if value.lower() == 'utf-8' else 3)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    spec = CommandSpec(
        category="core",
        stage="env_check",
        ticker="TNX",
        command=[sys.executable, str(script)],
        cwd=tmp_path,
    )

    result = run_command(spec)

    assert result.returncode == 0
    assert "utf-8" in result.stdout.lower()
