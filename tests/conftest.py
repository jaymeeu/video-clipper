"""Shared pytest fixtures. pytest auto-discovers this file and injects fixtures by name."""

import shutil
import subprocess
from pathlib import Path

import pytest

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
