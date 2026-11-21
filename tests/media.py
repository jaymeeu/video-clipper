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


def _ffmpeg_has_filter(name: str) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    # Lines look like: " .. subtitles         V->V       Render text subtitles..."
    return any(line.split()[1:2] == [name] for line in out.stdout.splitlines())


requires_libass = pytest.mark.skipif(
    not _ffmpeg_has_filter("subtitles"), reason="ffmpeg built without libass (no subtitles filter)"
)

requires_say = pytest.mark.skipif(
    shutil.which("say") is None, reason="needs macOS `say` to synthesise speech"
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
