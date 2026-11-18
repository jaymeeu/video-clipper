"""Thin, typed wrappers around the ffmpeg CLI."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """ffmpeg exited non-zero. Keeps the full stderr so callers can log or surface it."""

    def __init__(self, cmd: list[str], stderr: str) -> None:
        last_line = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
        super().__init__(f"ffmpeg failed: {last_line}")
        self.cmd = cmd
        self.stderr = stderr


def cut_clip(source: Path, output: Path, *, start: float, duration: float) -> Path:
    """Cut `duration` seconds from `source` starting at `start`, re-encoded to H.264/AAC MP4."""
    if not source.is_file():
        raise FileNotFoundError(f"source video not found: {source}")
    if start < 0 or duration <= 0:
        raise ValueError(f"invalid range: start={start}, duration={duration}")

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}",          # seek BEFORE -i: fast input seeking
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",      # moov atom up front so clips stream instantly
        str(output),
    ]  # fmt: skip
    logger.debug("running: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(cmd, result.stderr)

    logger.info("cut %.1fs clip at %.1fs -> %s", duration, start, output)
    return output
