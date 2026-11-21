"""Audio measurements, computed by streaming decoded samples out of ffmpeg."""

import logging
import subprocess
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from clippers.video import FFmpegError

logger = logging.getLogger(__name__)

# Loudness doesn't need hi-fi audio: 8 kHz keeps voices, crowds and music hits, and is
# half the data of Whisper's 16 kHz.
_SAMPLE_RATE = 8_000
_SILENCE_DB = -90.0  # floor for digital silence, where log10(0) would be -inf


def loudness_per_second(source: Path) -> NDArray[np.float64]:
    """Loudness of each second of `source`'s audio, in dBFS (0 = maximum, -90 = silence).

    Streams the audio from ffmpeg one second at a time, so memory use stays constant
    whether the video is 30 seconds or 3 hours long.
    """
    if not source.is_file():
        raise FileNotFoundError(f"source video not found: {source}")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
        "-f", "s16le", "-",  # raw signed 16-bit little-endian samples to stdout
    ]  # fmt: skip
    logger.debug("running: %s", " ".join(cmd))

    bytes_per_second = _SAMPLE_RATE * 2  # int16 = 2 bytes per sample
    levels: list[float] = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdout is not None and proc.stderr is not None  # we asked for PIPEs
        while chunk := proc.stdout.read(bytes_per_second):
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float64) / 32768.0
            rms = float(np.sqrt(np.mean(samples**2)))
            levels.append(20 * np.log10(rms) if rms > 0 else _SILENCE_DB)
        stderr = proc.stderr.read().decode(errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(cmd, stderr)

    logger.info("measured loudness for %d seconds of audio", len(levels))
    return np.maximum(np.array(levels, dtype=np.float64), _SILENCE_DB)
