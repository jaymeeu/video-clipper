"""Thin, typed wrappers around the ffmpeg CLI."""

import logging
import re
import subprocess
from pathlib import Path

from clippers.framing import Framing, framing_filter

logger = logging.getLogger(__name__)

# Filenames that need no escaping inside an ffmpeg filter graph.
_SAFE_FILTER_FILENAME = re.compile(r"[\w.-]+")


class FFmpegError(RuntimeError):
    """ffmpeg exited non-zero. Keeps the full stderr so callers can log or surface it."""

    def __init__(self, cmd: list[str], stderr: str) -> None:
        last_line = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
        super().__init__(f"ffmpeg failed: {last_line}")
        self.cmd = cmd
        self.stderr = stderr


def _run_ffmpeg(args: list[str], *, cwd: Path | None = None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    logger.debug("running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)
    if result.returncode != 0:
        raise FFmpegError(cmd, result.stderr)


def _validate_range(source: Path, start: float, duration: float) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"source video not found: {source}")
    if start < 0 or duration <= 0:
        raise ValueError(f"invalid range: start={start}, duration={duration}")


def extract_audio(source: Path, output: Path, *, start: float, duration: float) -> Path:
    """Extract a time range of `source` as 16 kHz mono WAV: the format Whisper works in."""
    _validate_range(source, start, duration)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)]
    )  # fmt: skip
    return output


def cut_clip(
    source: Path,
    output: Path,
    *,
    start: float,
    duration: float,
    framing: Framing = Framing.ORIGINAL,
    subtitles: Path | None = None,
) -> Path:
    """Cut `duration` seconds from `source` starting at `start`, re-encoded to H.264/AAC MP4.

    `framing` controls whether the clip is reframed (e.g. to vertical 9:16).
    `subtitles` is an .ass file to burn in; its times are relative to the clip start.
    """
    _validate_range(source, start, duration)

    filters = [framing_filter(framing)]
    cwd = None
    if subtitles is not None:
        if framing is Framing.ORIGINAL:
            raise ValueError("burned-in captions need vertical framing (crop or blur)")
        if not subtitles.is_file():
            raise FileNotFoundError(f"subtitles not found: {subtitles}")
        if not _SAFE_FILTER_FILENAME.fullmatch(subtitles.name):
            raise ValueError(f"subtitles filename must be plain [A-Za-z0-9_.-]: {subtitles.name}")
        # Paths inside a filter graph need two layers of escaping (':', '\', ',' ...).
        # Running ffmpeg *in* the subtitles' folder means we only ever pass a plain name.
        filters.append(f"subtitles=filename={subtitles.name}")
        cwd = subtitles.parent
        source, output = source.resolve(), output.resolve()

    video_filter = ",".join(f for f in filters if f)
    filter_args = ["-vf", video_filter] if video_filter else []

    output.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-ss", f"{start:.3f}",          # seek BEFORE -i: fast input seeking
            "-i", str(source),
            "-t", f"{duration:.3f}",
            *filter_args,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",          # 8-bit 4:2:0: the only format every phone plays
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",      # moov atom up front so clips stream instantly
            str(output),
        ],
        cwd=cwd,
    )  # fmt: skip

    logger.info(
        "cut %.1fs %s clip at %.1fs%s -> %s",
        duration, framing, start, " with captions" if subtitles else "", output,
    )  # fmt: skip
    return output
