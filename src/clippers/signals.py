"""Per-second highlight signals, each scaled to a common strength unit.

Every signal measures something different (dB, words per second, reaction count), so
each is divided by a REFERENCE value: the amount that counts as "clearly strong" for
that signal. After that, 1.0 means "strong" for every signal and they can be added.

The references and weights are first guesses. Tune them against real streams.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from clippers.highlights import FloatArray, above_baseline
from clippers.transcribe import Word

LOUDNESS_REFERENCE_DB = 10.0  # 10 dB above the local baseline: twice as loud to the ear
SPEECH_REFERENCE_WPS = 1.5  # talking 1.5 words/second faster than usual
REACTION_REFERENCE = 0.2  # reactions per second: ~6 in a 30 s clip

_SPEECH_SMOOTHING = 5  # seconds; per-second word counts are too jumpy on their own


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    strength: FloatArray  # one value per second, >= 0, 1.0 = clearly strong
    weight: float
    describe: Callable[[int, int], str]  # (start, duration) -> human-readable evidence

    def contribution(self, start: int, duration: int) -> float:
        """This signal's weighted mean strength over a window."""
        window = self.strength[start : start + duration]
        return self.weight * float(window.mean()) if window.size else 0.0


def combine(signals: Sequence[Signal]) -> FloatArray:
    """Weighted sum of the signals' strengths, second by second."""
    seconds = min(s.strength.size for s in signals)
    return np.sum([s.weight * s.strength[:seconds] for s in signals], axis=0)


def describe_window(signals: Sequence[Signal], start: int, duration: int) -> str:
    """Why a window was picked: the signals that contributed, strongest first."""
    ranked = sorted(signals, key=lambda s: s.contribution(start, duration), reverse=True)
    parts = [s.describe(start, duration) for s in ranked if s.contribution(start, duration) >= 0.05]
    return "; ".join(parts) or "slightly above the surrounding level"


# --- loudness ---------------------------------------------------------------------------


def loudness_signal(loudness_db: FloatArray) -> Signal:
    excess_db = above_baseline(loudness_db)

    def describe(start: int, duration: int) -> str:
        return f"{excess_db[start : start + duration].mean():.1f} dB louder than usual"

    return Signal("loudness", excess_db / LOUDNESS_REFERENCE_DB, 1.0, describe)


# --- speech rate ------------------------------------------------------------------------


def speech_rate(words: Sequence[Word], seconds: int) -> FloatArray:
    """Words per second, smoothed over a few seconds."""
    starts = np.array([int(w.start) for w in words if w.start < seconds], dtype=np.int64)
    counts = np.bincount(starts, minlength=seconds).astype(np.float64)
    kernel = np.full(_SPEECH_SMOOTHING, 1.0 / _SPEECH_SMOOTHING)
    return np.convolve(counts, kernel, mode="same")


def speech_signal(words: Sequence[Word], seconds: int) -> Signal:
    faster = above_baseline(speech_rate(words, seconds))

    def describe(start: int, duration: int) -> str:
        return f"talking {faster[start : start + duration].mean():.1f} words/s faster than usual"

    return Signal("speech", faster / SPEECH_REFERENCE_WPS, 0.5, describe)


# --- reactions --------------------------------------------------------------------------

# Single words and multi-word phrases that signal a reaction, in English and Nigerian
# Pidgin. Deliberately small and transparent; AI scoring will do this job properly.
REACTION_WORDS = frozenset(
    {
        # English
        "wow", "whoa", "omg", "insane", "crazy", "unbelievable", "yes", "goal",
        # Pidgin / Nigerian exclamations
        "omo", "chai", "haba", "kai", "wahala", "ehen", "ehn", "abeg", "jesu", "walahi",
        "gbam", "ah", "eh",
    }
)  # fmt: skip
REACTION_PHRASES: tuple[tuple[str, ...], ...] = (
    ("oh", "my", "god"),
    ("no", "way"),
    ("let's", "go"),
    ("what", "the"),
    ("na", "wa"),
    ("e", "don", "happen"),
    ("e", "choke"),
)
_LAUGHTER = re.compile(r"^(ha){2,}h?$|^(he){2,}$|^lol+$|^lmao+$")
_TOKEN_EDGES = re.compile(r"^[^\w']+|[^\w']+$")  # punctuation at either end of a word


def _token(text: str) -> str:
    return _TOKEN_EDGES.sub("", text.lower())


def reaction_events(words: Sequence[Word]) -> list[tuple[float, str]]:
    """(time, label) for every reaction found: hype words, phrases, laughter, '!'."""
    tokens = [_token(w.text) for w in words]
    events: list[tuple[float, str]] = []
    for i, word in enumerate(words):
        token = tokens[i]
        if token in REACTION_WORDS:
            events.append((word.start, token))
        elif _LAUGHTER.match(token):
            events.append((word.start, "laughter"))
        elif word.text.endswith("!"):
            events.append((word.start, f"{token}!"))
        for phrase in REACTION_PHRASES:
            if tuple(tokens[i : i + len(phrase)]) == phrase:
                events.append((word.start, " ".join(phrase)))
    return events


def reaction_signal(words: Sequence[Word], seconds: int) -> Signal:
    events = [(t, label) for t, label in reaction_events(words) if t < seconds]
    counts = np.bincount(
        np.array([int(t) for t, _ in events], dtype=np.int64), minlength=seconds
    ).astype(np.float64)

    def describe(start: int, duration: int) -> str:
        labels = [label for t, label in events if start <= t < start + duration]
        unique = list(dict.fromkeys(labels))  # de-duplicate, keeping first-seen order
        shown = ", ".join(f"'{label}'" for label in unique[:4])
        return f"{len(labels)} reactions ({shown})"

    return Signal("reactions", counts / REACTION_REFERENCE, 1.0, describe)
