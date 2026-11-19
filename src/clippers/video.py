"""Thin, typed wrappers around the ffmpeg CLI."""

import logging
import subprocess
from pathlib import Path

from clippers.framing import Framing, framing_filter

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """ffmpeg exited non-zero. Keeps the full stderr so callers can log or surface it."""

    def __init__(self, cmd: list[str], stderr: str) -> None:
        last_line = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
        super().__init__(f"ffmpeg failed: {last_line}")
        self.cmd = cmd
        self.stderr = stderr


def cut_clip(
    source: Path,
    output: Path,
    *,
    start: float,
    duration: float,
    framing: Framing = Framing.ORIGINAL,
) -> Path:
    """Cut `duration` seconds from `source` starting at `start`, re-encoded to H.264/AAC MP4.

    `framing` controls whether the clip is reframed (e.g. to vertical 9:16).
    """
    if not source.is_file():
        raise FileNotFoundError(f"source video not found: {source}")
    if start < 0 or duration <= 0:
        raise ValueError(f"invalid range: start={start}, duration={duration}")

    video_filter = framing_filter(framing)
    filter_args = ["-vf", video_filter] if video_filter else []

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}",          # seek BEFORE -i: fast input seeking
        "-i", str(source),
        "-t", f"{duration:.3f}",
        *filter_args,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",          # 8-bit 4:2:0: the only format every phone plays
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",      # moov atom up front so clips stream instantly
        str(output),
    ]  # fmt: skip
    logger.debug("running: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(cmd, result.stderr)

    logger.info("cut %.1fs %s clip at %.1fs -> %s", duration, framing, start, output)
    return output
