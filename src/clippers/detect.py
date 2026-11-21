"""Turn a video into a moments file by measuring it. Glue between I/O and the scoring."""

import logging
from pathlib import Path

from clippers.audio import loudness_per_second
from clippers.highlights import find_highlights
from clippers.ingest import is_url
from clippers.moments import Moment, MomentsFile
from clippers.signals import (
    Signal,
    combine,
    describe_window,
    loudness_signal,
    reaction_signal,
    speech_signal,
)
from clippers.transcribe import Transcript

logger = logging.getLogger(__name__)


class NoHighlightsError(ValueError):
    """Nothing in the video stood out enough to pick."""


def detect_moments(
    source: str,
    video: Path,
    *,
    count: int,
    duration: int,
    transcript: Transcript | None = None,
) -> MomentsFile:
    """Pick up to `count` highlight moments from `video` and describe them as a MomentsFile.

    Loudness is always used. With a `transcript` (times relative to the start of the
    video), speech-rate and reaction signals are added.

    `source` is what the user typed (URL or path); it's stored in the file so `batch`
    can find the video again. Local paths are stored absolute, because the moments
    file may be saved somewhere else and relative paths resolve from its folder.
    """
    loudness = loudness_per_second(video)
    seconds = loudness.size
    signals: list[Signal] = [loudness_signal(loudness)]
    if transcript is not None:
        signals += [
            speech_signal(transcript.words, seconds),
            reaction_signal(transcript.words, seconds),
        ]
    logger.info("scoring with signals: %s", ", ".join(s.name for s in signals))

    picks = find_highlights(combine(signals), count=count, duration=duration)
    if not picks:
        raise NoHighlightsError(
            "no moment stood out from the rest of the video (is it silent, or evenly loud?)"
        )

    moments = [
        Moment(
            start=h.start,
            duration=h.duration,
            score=h.score,
            reason=describe_window(signals, h.start, h.duration),
        )
        for h in picks
    ]
    logger.info("picked %d of %d requested moments", len(moments), count)
    stored_source = source if is_url(source) else str(video.resolve())
    return MomentsFile(source=stored_source, moments=moments)
