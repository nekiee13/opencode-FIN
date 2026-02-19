from __future__ import annotations

from pathlib import Path


def test_load_dotenv_if_present_basic(monkeypatch, tmp_path: Path) -> None:
    from src.config.paths import load_dotenv_if_present

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "# comment",
                "FIN_DYNAMIX_REPO=F:/repo/DynaMix-python",
                "export FIN_DYNAMIX_PY_EXE=F:/venv/python.exe",
                'FIN_QUOTED="hello world"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("FIN_DYNAMIX_REPO", raising=False)
    monkeypatch.delenv("FIN_DYNAMIX_PY_EXE", raising=False)
    monkeypatch.delenv("FIN_QUOTED", raising=False)

    loaded = load_dotenv_if_present(dotenv)

    assert loaded["FIN_DYNAMIX_REPO"] == "F:/repo/DynaMix-python"
    assert loaded["FIN_DYNAMIX_PY_EXE"] == "F:/venv/python.exe"
    assert loaded["FIN_QUOTED"] == "hello world"


def test_load_dotenv_if_present_respects_override_flag(
    monkeypatch, tmp_path: Path
) -> None:
    from src.config.paths import load_dotenv_if_present

    dotenv = tmp_path / ".env"
    dotenv.write_text("FIN_DYNAMIX_REPO=from_file", encoding="utf-8")

    monkeypatch.setenv("FIN_DYNAMIX_REPO", "from_env")

    loaded_default = load_dotenv_if_present(dotenv, override=False)
    assert "FIN_DYNAMIX_REPO" not in loaded_default

    loaded_override = load_dotenv_if_present(dotenv, override=True)
    assert loaded_override["FIN_DYNAMIX_REPO"] == "from_file"
