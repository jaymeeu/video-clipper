"""Settings from a .env file: loaded by the CLI, never overriding real environment vars."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from clippers.ai import OpenAISuggester
from clippers.cli import app, load_env_file

KEYS = ("OPENAI_API_KEY", "CLIPPERS_AI_MODEL", "CLIPPERS_CACHE_DIR")


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty project folder as the cwd, with none of our settings in the environment.

    monkeypatch.delenv records the original values and restores them afterwards, which
    also undoes anything load_dotenv sets during the test.
    """
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_loads_env_file_from_current_folder(project: Path) -> None:
    (project / ".env").write_text("OPENAI_API_KEY=sk-from-file\n")

    assert load_env_file() == project / ".env"
    assert os.environ["OPENAI_API_KEY"] == "sk-from-file"


def test_finds_env_file_in_a_parent_folder(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / ".env").write_text("CLIPPERS_AI_MODEL=from-parent\n")
    nested = project / "output" / "clips"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    load_env_file()

    assert os.environ["CLIPPERS_AI_MODEL"] == "from-parent"


def test_real_environment_wins_over_file(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / ".env").write_text("OPENAI_API_KEY=sk-from-file\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-shell")

    load_env_file()

    assert os.environ["OPENAI_API_KEY"] == "sk-from-shell"


def test_no_env_file_is_fine(project: Path) -> None:
    assert load_env_file() is None


def test_ai_model_from_env_file_reaches_the_suggester(project: Path) -> None:
    # Regression: the model was read into a module constant at import time, before the
    # CLI loads .env, so CLIPPERS_AI_MODEL in .env was silently ignored.
    (project / ".env").write_text("OPENAI_API_KEY=sk-test\nCLIPPERS_AI_MODEL=gpt-from-file\n")

    load_env_file()

    assert OpenAISuggester().model == "gpt-from-file"


def test_cli_loads_env_file(project: Path) -> None:
    # CLIPPERS_CACHE_DIR is harmless to set and observable: proves the CLI loaded the file.
    (project / ".env").write_text(f"CLIPPERS_CACHE_DIR={project / 'cache'}\n")

    CliRunner().invoke(app, ["download", "not-a-url"])  # any command runs the callback

    assert os.environ["CLIPPERS_CACHE_DIR"] == str(project / "cache")
