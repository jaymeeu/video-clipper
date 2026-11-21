"""Move clip edges to natural breaks in speech, so nobody is cut off mid-sentence.

Pure functions over transcript words: no I/O.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence

from clippers.transcribe import Word

_SENTENCE_END = (".", "?", "!")
PAUSE = 0.6  # seconds of silence between words that counts as a break
MAX_SHIFT = 4.0  # never move an edge further than this to find a break
LEAD_IN = 0.25  # start slightly before the first word, so its first sound isn't clipped
TAIL = 0.4  # and end slightly after the last word
_JUST_BEFORE = 0.05  # seconds


def breaks(words: Sequence[Word]) -> tuple[list[float], list[float]]:
    """(phrase starts, phrase ends): where it's natural to begin or end a clip.

    A break falls between two words when the first ends a sentence or there's a pause.
    The first word always starts a phrase and the last always ends one.
    """
    if not words:
        return [], []
    starts: list[float] = [words[0].start]
    ends: list[float] = []
    for before, after in zip(words, words[1:], strict=False):
        if before.text.endswith(_SENTENCE_END) or after.start - before.end >= PAUSE:
            ends.append(before.end)
            starts.append(after.start)
    ends.append(words[-1].end)
    return starts, ends


def _speaking_at(words: Sequence[Word], t: float) -> bool:
    """Is someone mid-phrase at time t (inside a word, or in a short gap between words)?"""
    i = bisect_right([w.start for w in words], t) - 1  # last word starting at or before t
    if i < 0 or i + 1 >= len(words):
        return 0 <= i < len(words) and t < words[i].end
    before, after = words[i], words[i + 1]
    in_phrase_gap = after.start - before.end < PAUSE and not before.text.endswith(_SENTENCE_END)
    return t < before.end or in_phrase_gap


def snap_span(
    start: float,
    end: float,
    words: Sequence[Word],
    *,
    video_seconds: float,
    max_shift: float = MAX_SHIFT,
) -> tuple[float, float]:
    """Widen [start, end] to the nearest phrase breaks, by at most `max_shift` each side.

    The start moves back to where the current phrase began; the end moves forward to
    where the current phrase finishes. Edges that already fall in a pause stay put. If
    no break is close enough, the edge is left alone: a clipped word beats a clip that
    wanders far from the moment.
    """
    starts, ends = breaks(words)
    if not starts:
        return start, end

    new_start = start
    if _speaking_at(words, start):
        i = bisect_right(starts, start) - 1  # latest phrase start at or before `start`
        if i >= 0 and start - starts[i] <= max_shift:
            new_start = starts[i] - LEAD_IN

    new_end = end
    # Look just *before* the end: an end landing exactly where a new phrase starts means
    # "stop before it", not "include it".
    if _speaking_at(words, end - _JUST_BEFORE):
        j = bisect_left(ends, end)  # earliest phrase end at or after `end`
        if j < len(ends) and ends[j] - end <= max_shift:
            new_end = ends[j] + TAIL

    return max(0.0, new_start), min(video_seconds, new_end)
