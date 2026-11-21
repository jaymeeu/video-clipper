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

from clippers import cache

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

    def between(self, start: float, end: float) -> "Transcript":
        """The words spoken in [start, end), re-timed so `start` becomes 0.

        A word counts if it starts inside the range; its end is cut at the range end.
        """
        words = [
            Word(
                text=w.text,
                start=w.start - start,
                end=min(w.end, end) - start,
                probability=w.probability,
            )
            for w in self.words
            if start <= w.start < end
        ]
        return self.model_copy(update={"words": words})


@lru_cache(maxsize=2)
def _load_model(name: str) -> "WhisperModel":
    """Load a Whisper model: from the local cache if present, otherwise download it once.

    Trying the cache first means no network request on every run, so clipping a local
    file works offline. Cached per process: loading takes seconds.
    """
    # Deferred imports keep `clippers --help` instant.
    from faster_whisper import WhisperModel  # pyright: ignore[reportMissingTypeStubs]
    from huggingface_hub.errors import LocalEntryNotFoundError

    # int8 on CPU: ~4x less memory than float32 and much faster, for a tiny accuracy cost.
    try:
        model = WhisperModel(name, device="cpu", compute_type="int8", local_files_only=True)
    except LocalEntryNotFoundError:
        # Must come before any generic FileNotFoundError handling: it's a subclass of it.
        logger.info("downloading whisper model %r (one time only)", name)
        model = WhisperModel(name, device="cpu", compute_type="int8")
    logger.info("loaded whisper model %r", name)
    return model


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


def _cache_file(video: Path, model: str, language: str | None) -> Path:
    """The cache key is the file's path, size and modification time plus the model and
    language. Hashing the contents would be more exact but means reading gigabytes on
    every run; if the file is replaced, its size or mtime changes and the cache misses.
    """
    stat = video.stat()  # raises FileNotFoundError for a missing video
    return cache.cache_path(
        "transcripts",
        str(video.resolve()), str(stat.st_size), str(stat.st_mtime_ns), model, str(language),
    )  # fmt: skip


def load_cached_transcript(
    video: Path, *, model: str = DEFAULT_MODEL, language: str | None = None
) -> Transcript | None:
    """The cached whole-video transcript if there is one. Never transcribes."""
    return cache.load(_cache_file(video, model, language), Transcript)


def transcribe_cached(
    video: Path, *, model: str = DEFAULT_MODEL, language: str | None = None
) -> Transcript:
    """Transcribe a whole video, reusing a cached result when nothing has changed."""
    path = _cache_file(video, model, language)
    if (cached := cache.load(path, Transcript)) is not None:
        logger.info("using cached transcript (%d words)", len(cached.words))
        return cached

    logger.info("transcribing the whole video; cached afterwards, so this happens once")
    transcript = transcribe(video, model=model, language=language)
    cache.save(path, transcript)
    return transcript
