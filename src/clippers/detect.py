"""Turn a video into a moments file by measuring it. Glue between I/O and the scoring."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clippers.ai import AIMoment
from clippers.audio import loudness_per_second
from clippers.boundaries import snap_span
from clippers.highlights import Highlight, find_highlights
from clippers.ingest import is_url
from clippers.moments import Moment, MomentsFile
from clippers.signals import (
    Signal,
    ai_signal,
    best_ai_moment,
    combine,
    describe_window,
    loudness_signal,
    reaction_signal,
    speech_signal,
)
from clippers.transcribe import Transcript, Word

logger = logging.getLogger(__name__)


MIN_CLIP = 8.0  # seconds
MAX_CLIP = 90.0
_CANDIDATES_PER_CLIP = 3  # ask for extra picks: merging overlaps can drop some


class NoHighlightsError(ValueError):
    """Nothing in the video stood out enough to pick."""


@dataclass(frozen=True, slots=True)
class Span:
    """A refined clip: real start/end seconds, possibly tied to an AI suggestion."""

    start: float
    end: float
    score: float
    ai: AIMoment | None

    @property
    def duration(self) -> float:
        return self.end - self.start


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def refine(
    picks: Sequence[Highlight],
    *,
    count: int,
    video_seconds: float,
    words: Sequence[Word] = (),
    ai_moments: Sequence[AIMoment] = (),
) -> list[Span]:
    """Turn fixed-length picks (best first) into at most `count` well-cut, distinct clips.

    1. A pick that mostly overlaps an AI moment takes that moment's span (and title):
       the AI chose where the moment starts and ends, build-up included.
    2. Edges snap to the nearest phrase break, so nobody is cut off mid-sentence.
    3. Length is kept within MIN_CLIP..MAX_CLIP.
    4. A clip that mostly covers one already kept is dropped: one moment, one clip.
    """
    spans: list[Span] = []
    for pick in picks:
        start, end = float(pick.start), float(pick.start + pick.duration)
        ai = best_ai_moment(ai_moments, pick.start, pick.duration)
        if ai is not None and _overlap(ai.start, ai.end, start, end) >= 0.5 * min(
            ai.end - ai.start, end - start
        ):
            start, end = ai.start, ai.end
        else:
            ai = None  # only a passing overlap: don't borrow its title
        if words:
            start, end = snap_span(start, end, words, video_seconds=video_seconds)
        end = min(end, start + MAX_CLIP)
        if end - start < MIN_CLIP:
            end = min(video_seconds, start + MIN_CLIP)

        if any(
            _overlap(start, end, kept.start, kept.end) > 0.5 * min(end - start, kept.duration)
            for kept in spans
        ):
            logger.debug("dropping %.0f-%.0fs: same moment as a better pick", start, end)
            continue
        spans.append(Span(start=start, end=end, score=pick.score, ai=ai))
        if len(spans) == count:
            break
    return spans


def detect_moments(
    source: str,
    video: Path,
    *,
    count: int,
    duration: int,
    transcript: Transcript | None = None,
    ai_moments: Sequence[AIMoment] = (),
) -> MomentsFile:
    """Pick up to `count` highlight moments from `video` and describe them as a MomentsFile.

    Loudness is always used. With a `transcript` (times relative to the start of the
    video), speech-rate and reaction signals are added; with `ai_moments`, an AI signal,
    and picks take their title from the AI suggestion they overlap most.

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
    if ai_moments:
        signals.append(ai_signal(ai_moments, seconds))
    logger.info("scoring with signals: %s", ", ".join(s.name for s in signals))

    picks = find_highlights(combine(signals), count=count * _CANDIDATES_PER_CLIP, duration=duration)
    spans = refine(
        picks,
        count=count,
        video_seconds=float(seconds),
        words=transcript.words if transcript else (),
        ai_moments=ai_moments,
    )
    if not spans:
        raise NoHighlightsError(
            "no moment stood out from the rest of the video (is it silent, or evenly loud?)"
        )

    moments = [
        Moment(
            start=round(span.start, 2),
            duration=round(span.duration, 2),
            title=span.ai.title if span.ai else None,
            score=span.score,
            reason=describe_window(signals, int(span.start), max(1, round(span.duration))),
        )
        for span in spans
    ]
    logger.info("picked %d of %d requested moments", len(moments), count)
    stored_source = source if is_url(source) else str(video.resolve())
    return MomentsFile(source=stored_source, moments=moments)
