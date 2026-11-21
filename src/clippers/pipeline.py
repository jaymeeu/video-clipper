"""End-to-end clip production. The CLI calls this today; the API will call it in Phase 3."""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from clippers.captions import write_ass
from clippers.framing import Framing
from clippers.transcribe import DEFAULT_MODEL, Transcript, transcribe
from clippers.video import cut_clip, extract_audio, probe_duration

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CaptionOptions:
    model: str = DEFAULT_MODEL
    language: str | None = None  # None = auto-detect


@dataclass(frozen=True, slots=True)
class ClipResult:
    path: Path
    transcript: Transcript | None


def make_clip(
    source: Path,
    output: Path,
    *,
    start: float,
    duration: float,
    framing: Framing = Framing.BLUR,
    captions: CaptionOptions | None = None,
    transcript: Transcript | None = None,
) -> ClipResult:
    """Cut one clip, optionally transcribing it and burning in word-highlighted captions.

    `transcript` is an existing transcript of the *whole* video. When given, the clip's
    captions are cut out of it, skipping audio extraction and Whisper entirely.

    A clip that runs past the end of the video is shortened (with a warning); one that
    starts past the end raises ValueError. ffmpeg itself would "succeed" with an empty file.
    """
    duration = _fit_to_video(source, start, duration)
    if captions is None:
        path = cut_clip(source, output, start=start, duration=duration, framing=framing)
        return ClipResult(path=path, transcript=None)

    with tempfile.TemporaryDirectory(prefix="clippers-") as tmp:
        work = Path(tmp)
        if transcript is not None:
            clip_transcript = transcript.between(start, start + duration)
        else:
            audio = extract_audio(source, work / "audio.wav", start=start, duration=duration)
            clip_transcript = transcribe(audio, model=captions.model, language=captions.language)

        subtitles = None
        if clip_transcript.words:
            subtitles = write_ass(clip_transcript.words, work / "captions.ass")
        else:
            logger.warning("no speech detected; clip will have no captions")

        path = cut_clip(
            source, output, start=start, duration=duration, framing=framing, subtitles=subtitles
        )
    return ClipResult(path=path, transcript=clip_transcript)


_MIN_CLIP = 0.5  # seconds; anything shorter isn't a usable clip


def _fit_to_video(source: Path, start: float, duration: float) -> float:
    length = probe_duration(source)
    if length is None:
        return duration  # unknown length: trust the caller
    if start > length - _MIN_CLIP:
        raise ValueError(f"start {start:.1f}s is past the end of the video ({length:.1f}s long)")
    if start + duration > length:
        trimmed = length - start
        logger.warning(
            "clip at %.1fs runs past the end of the video; shortened %.1fs -> %.1fs",
            start, duration, trimmed,
        )  # fmt: skip
        return trimmed
    return duration
