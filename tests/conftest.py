"""Shared pytest fixtures. pytest auto-discovers this file and injects fixtures by name."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 10s 320x240 test-pattern video with a sine tone, generated once per test run."""
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440",
        "-t", "10", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path
