"""Find highlight moments in a per-second strength signal.

Pure numpy functions: they take arrays (one value per second of video) and return
picks. No I/O, so they're fast to test with hand-made arrays. What the strength is
made of (loudness, speech, reactions...) is decided in signals.py.
"""

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

# Strength units: each signal is scaled so 1.0 means "clearly strong" (see signals.py).
# 0.1 is a tenth of that, e.g. ~1 dB of loudness alone: about the smallest change people
# notice. Windows below it aren't highlights.
MIN_SCORE = 0.1


@dataclass(frozen=True, slots=True)
class Highlight:
    start: int  # seconds
    duration: int  # seconds
    score: float  # centre-weighted mean strength across the window


def above_baseline(signal: FloatArray, *, baseline_seconds: int = 120) -> FloatArray:
    """How far each second sits above the median of its surroundings (never negative).

    Works for any per-second measurement: loudness in dB, words per second, ... A median
    ignores short spikes, so the baseline tracks "normal for this part of the stream":
    a shout during a quiet chat stands out, the same volume during loud music doesn't.
    """
    if signal.size == 0:
        return signal.copy()
    half = baseline_seconds // 2
    # Mirror the data at both ends so the first/last minute still has a baseline. Not
    # mode="edge": that repeats the single first value 60 times, and streams often open
    # with a silent second, which made the whole opening minute look "loud".
    padded = np.pad(signal, half, mode="reflect")
    windows = sliding_window_view(padded, 2 * half + 1)  # one row per second; no copying
    baseline = np.median(windows, axis=1)
    return np.clip(signal - baseline, 0.0, None)


def window_scores(signal: FloatArray, duration: int) -> FloatArray:
    """Centre-weighted mean of `signal` over every `duration`-second window.

    Index i = the window starting at second i. The weights are a bell curve (Hann
    window), so a burst scores highest when it sits in the *middle* of the clip:
    build-up before it, reaction after. A flat average would score every window that
    contains the burst equally and pick the earliest, leaving the burst at the very end.
    """
    if signal.size == 0:
        return signal.copy()
    if signal.size <= duration:
        return np.array([signal.mean()])  # video shorter than one clip: one window, at 0
    weights = np.hanning(duration + 2)[1:-1]  # drop the zero endpoints
    kernel = weights / weights.sum()
    return np.convolve(signal, kernel, mode="valid")


def pick_windows(
    scores: FloatArray, *, duration: int, count: int, min_score: float = MIN_SCORE
) -> list[tuple[int, float]]:
    """Greedily take the best-scoring windows that don't overlap, best first.

    Stops early when nothing left reaches `min_score`: a calm video yields fewer picks
    rather than padding the list with dull moments.
    """
    remaining = scores.astype(np.float64)  # a copy: we overwrite taken regions below
    picks: list[tuple[int, float]] = []
    while len(picks) < count and remaining.size:
        best = int(np.argmax(remaining))
        score = float(remaining[best])
        if not score >= min_score:  # also catches -inf (everything taken)
            break
        picks.append((best, score))
        # Any window starting within `duration` of this one would overlap it.
        remaining[max(0, best - duration + 1) : best + duration] = -np.inf
    return picks


def find_highlights(
    strength: FloatArray, *, count: int = 5, duration: int = 30, min_score: float = MIN_SCORE
) -> list[Highlight]:
    """The `count` best non-overlapping `duration`-second windows of a strength signal."""
    scores = window_scores(strength, duration)
    clip_length = min(duration, strength.size)
    return [
        Highlight(start=start, duration=clip_length, score=round(score, 3))
        for start, score in pick_windows(
            scores, duration=duration, count=count, min_score=min_score
        )
    ]
