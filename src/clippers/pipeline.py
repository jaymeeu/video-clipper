"""End-to-end clip production. The CLI calls this today; the API will call it in Phase 3."""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from clippers.captions import write_ass
from clippers.framing import Framing
from clippers.transcribe import DEFAULT_MODEL, Transcript, transcribe
from clippers.video import cut_clip, extract_audio

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
) -> ClipResult:
    """Cut one clip, optionally transcribing it and burning in word-highlighted captions."""
    if captions is None:
        path = cut_clip(source, output, start=start, duration=duration, framing=framing)
        return ClipResult(path=path, transcript=None)

    with tempfile.TemporaryDirectory(prefix="clippers-") as tmp:
        work = Path(tmp)
        audio = extract_audio(source, work / "audio.wav", start=start, duration=duration)
        transcript = transcribe(audio, model=captions.model, language=captions.language)

        subtitles = None
        if transcript.words:
            subtitles = write_ass(transcript.words, work / "captions.ass")
        else:
            logger.warning("no speech detected; clip will have no captions")

        path = cut_clip(
            source, output, start=start, duration=duration, framing=framing, subtitles=subtitles
        )
    return ClipResult(path=path, transcript=transcript)
