"""Speech-to-text with word-level timestamps, via faster-whisper.

faster-whisper's type hints are incomplete, so this module is the boundary: the
`pyright: ignore` comments below are confined here, and everything outside sees only
our fully typed Transcript/Word models.
"""

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # only for type checkers: importing faster_whisper is slow
    from faster_whisper import WhisperModel  # pyright: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "small"


class Word(BaseModel):
    """One spoken word. Times are seconds from the start of the transcribed audio."""

    model_config = ConfigDict(frozen=True)

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class Transcript(BaseModel):
    language: str
    language_probability: float = Field(ge=0, le=1)
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@lru_cache(maxsize=2)
def _load_model(name: str) -> "WhisperModel":
    """Load (and on first use, download) a Whisper model. Cached: loading takes seconds."""
    # Deferred import keeps `clippers --help` instant.
    from faster_whisper import WhisperModel  # pyright: ignore[reportMissingTypeStubs]

    logger.info("loading whisper model %r (first run downloads it)", name)
    # int8 on CPU: ~4x less memory than float32 and much faster, for a tiny accuracy cost.
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(
    audio: Path, *, model: str = DEFAULT_MODEL, language: str | None = None
) -> Transcript:
    """Transcribe `audio` (any format ffmpeg/PyAV can read) into timed words.

    `language` is an ISO code like "en"; None lets Whisper detect it.
    """
    if not audio.is_file():
        raise FileNotFoundError(f"audio not found: {audio}")

    whisper = _load_model(model)
    began = time.perf_counter()
    # Its signature has one `dict` param with no key/value types (vad_parameters).
    segments, info = whisper.transcribe(  # pyright: ignore[reportUnknownMemberType]
        str(audio),
        language=language,
        word_timestamps=True,
        vad_filter=True,  # skip silence: faster, and stops Whisper inventing text in quiet parts
        condition_on_previous_text=False,  # avoids repetition loops on long or noisy audio
    )
    # `segments` is a lazy generator: the actual transcription happens while we iterate.
    words = [
        Word(text=w.word.strip(), start=w.start, end=w.end, probability=w.probability)
        for segment in segments
        for w in segment.words or []
        if w.word.strip()
    ]

    elapsed = time.perf_counter() - began
    logger.info(
        "transcribed %.1fs of audio in %.1fs (%.2fx realtime), %d words, language=%s",
        info.duration,
        elapsed,
        info.duration / elapsed if elapsed else 0.0,
        len(words),
        info.language,
    )
    return Transcript(
        language=info.language, language_probability=info.language_probability, words=words
    )
