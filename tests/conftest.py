"""Shared pytest fixtures. pytest auto-discovers this file and injects fixtures by name."""

import logging
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from clippers import netguard
from tests.media import MakeVideo


@pytest.fixture(scope="session")
def make_video(tmp_path_factory: pytest.TempPathFactory) -> MakeVideo:
    """Factory: generate a test-pattern video with a sine tone. Cached per (size, length).

    Skips (rather than errors) any test that uses it when ffmpeg isn't installed.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    cache: dict[tuple[int, int, float], Path] = {}

    def _make(width: int = 320, height: int = 240, seconds: float = 10.0) -> Path:
        key = (width, height, seconds)
        if key not in cache:
            path = tmp_path_factory.mktemp("media") / f"{width}x{height}_{seconds:g}s.mp4"
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440",
                "-t", f"{seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                str(path),
            ]  # fmt: skip
            subprocess.run(cmd, check=True, capture_output=True)
            cache[key] = path
        return cache[key]

    return _make


@pytest.fixture(scope="session")
def sample_video(make_video: MakeVideo) -> Path:
    """The default 10s 320x240 test video."""
    return make_video()


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """Put logging back as it was after every test.

    The CLI's callback reconfigures logging globally; without this, one test's settings
    leak into the next and tests pass or fail depending on the order they run in.
    """
    root, ours = logging.getLogger(), logging.getLogger("clippers")
    saved = (root.level, list(root.handlers), ours.level)
    yield
    root.setLevel(saved[0])
    root.handlers[:] = saved[1]
    ours.setLevel(saved[2])


@pytest.fixture(autouse=True)
def isolate_from_real_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make it impossible for a test to use the developer's real credentials or files.

    - our settings are removed from the environment (API key, AI model);
    - the cwd is a fresh temp folder, so the CLI's .env search never finds the project's
      real .env (and no test can write output/ or downloads/ into the repo);
    - the cache points at a temp folder, never ~/.cache/clippers;
    - OpenAI is pointed at a port that refuses connections, so even a test that slips
      through makes no paid request: it fails fast instead;
    - the SSRF guard's DNS lookup answers with a public address instead of asking real
      DNS (tests that need another answer patch netguard._resolve themselves).
    Tests that need any of these set them explicitly (monkeypatch.setenv/chdir).
    """
    for key in ("OPENAI_API_KEY", "CLIPPERS_AI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLIPPERS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/no-network-in-tests")
    monkeypatch.setattr(netguard, "_resolve", lambda host, port: ["8.8.8.8"])
    monkeypatch.chdir(tmp_path)
