"""Turn a video into a moments file by measuring it. Glue between I/O and highlights.py."""

import logging
from pathlib import Path

from clippers.audio import loudness_per_second
from clippers.highlights import find_loud_moments
from clippers.ingest import is_url
from clippers.moments import Moment, MomentsFile

logger = logging.getLogger(__name__)


class NoHighlightsError(ValueError):
    """Nothing in the video stood out enough to pick."""


def detect_moments(source: str, video: Path, *, count: int, duration: int) -> MomentsFile:
    """Pick up to `count` highlight moments from `video` and describe them as a MomentsFile.

    `source` is what the user typed (URL or path); it's stored in the file so `batch`
    can find the video again. Local paths are stored absolute, because the moments
    file may be saved somewhere else and relative paths resolve from its folder.
    """
    loudness = loudness_per_second(video)
    picks = find_loud_moments(loudness, count=count, duration=duration)
    if not picks:
        raise NoHighlightsError(
            "no moment stood out from the rest of the audio (is the video silent, or evenly loud?)"
        )

    moments = [
        Moment(
            start=h.start,
            duration=h.duration,
            score=h.score,
            reason=f"audio averages {h.score:.1f} dB louder than the surrounding two minutes",
        )
        for h in picks
    ]
    logger.info("picked %d of %d requested moments", len(moments), count)
    stored_source = source if is_url(source) else str(video.resolve())
    return MomentsFile(source=stored_source, moments=moments)
