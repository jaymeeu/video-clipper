"""Plain test helpers for media files. Import these explicitly; fixtures live in conftest.py."""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

type MakeVideo = Callable[..., Path]
"""Signature of the `make_video` fixture: make_video(width, height, seconds) -> Path."""

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


def probe_duration(path: Path) -> float:
    """Container duration in seconds, via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


def probe_size(path: Path) -> tuple[int, int]:
    """(width, height) of the first video stream, via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
    ]  # fmt: skip
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    width, height = out.stdout.strip().split(",")
    return int(width), int(height)
