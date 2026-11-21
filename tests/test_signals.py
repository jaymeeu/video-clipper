import numpy as np
import pytest

from clippers.signals import (
    Signal,
    combine,
    describe_window,
    loudness_signal,
    reaction_events,
    reaction_signal,
    speech_rate,
    speech_signal,
)
from clippers.transcribe import Word


def said(*timed: tuple[float, str]) -> list[Word]:
    """Words from (start_time, text) pairs, each 0.3s long."""
    return [Word(text=t, start=s, end=s + 0.3, probability=0.9) for s, t in timed]


def flat(seconds: int, value: float = 0.0) -> np.ndarray:
    return np.full(seconds, value)


class TestReactionEvents:
    @pytest.mark.parametrize(
        ("text", "label"),
        [
            ("Omo,", "omo"),
            ("CHAI!", "chai"),
            ("hahaha", "laughter"),
            ("Hehehe.", "laughter"),
            ("lol", "laughter"),
            ("goal", "goal"),
            ("Mad!", "mad!"),  # any exclamation counts
        ],
    )
    def test_single_word_reactions(self, text: str, label: str) -> None:
        assert reaction_events(said((5.0, text))) == [(5.0, label)]

    def test_phrases_across_words(self) -> None:
        events = reaction_events(said((1, "No"), (1.3, "way."), (8, "Na"), (8.3, "wa"), (8.6, "o")))

        assert (1, "no way") in events
        assert (8, "na wa") in events

    def test_ordinary_speech_has_no_reactions(self) -> None:
        assert reaction_events(said((0, "we"), (0.4, "dey"), (0.8, "here"), (1.2, "today."))) == []


class TestSignals:
    def test_speech_rate_counts_words_per_second(self) -> None:
        words = said(*[(10 + i * 0.2, "word") for i in range(25)])  # 5 words/s for 5 s

        rate = speech_rate(words, 30)

        assert rate[12] == pytest.approx(5.0)
        assert rate[25] == pytest.approx(0.0)

    def test_fast_speech_scores_on_speech_signal(self) -> None:
        normal = [(t * 1.0, "word") for t in range(0, 300)]  # 1 word/s all along
        burst = [(150 + i * 0.25, "word") for i in range(40)]  # +4 words/s for 10 s
        signal = speech_signal(said(*normal, *burst), 300)

        assert signal.strength[155] > 1.0  # well above the 1.5 words/s reference
        assert signal.strength[50] == pytest.approx(0)
        assert "faster than usual" in signal.describe(150, 10)

    def test_reaction_signal_describes_what_was_said(self) -> None:
        signal = reaction_signal(said((3, "Omo!"), (4, "no"), (4.3, "way"), (40, "chai")), 60)

        assert signal.strength[3] > 0
        assert signal.describe(0, 30) == "2 reactions ('omo', 'no way')"

    def test_loudness_signal_is_in_reference_units(self) -> None:
        loudness = flat(300, -30)
        loudness[100:110] = -10  # +20 dB

        signal = loudness_signal(loudness)

        assert signal.strength[105] == pytest.approx(2.0)  # 20 dB / 10 dB reference
        assert signal.describe(100, 10) == "20.0 dB louder than usual"


def test_combine_weights_and_trims_to_shortest() -> None:
    a = Signal("a", flat(10, 1.0), 1.0, lambda s, d: "a")
    b = Signal("b", flat(8, 2.0), 0.5, lambda s, d: "b")

    combined = combine([a, b])

    assert combined.size == 8
    assert combined[0] == pytest.approx(2.0)  # 1*1.0 + 0.5*2.0


def test_describe_window_lists_contributors_strongest_first() -> None:
    weak = Signal("weak", flat(60, 0.2), 1.0, lambda s, d: "weak evidence")
    strong = Signal("strong", flat(60, 0.9), 1.0, lambda s, d: "strong evidence")
    silent = Signal("silent", flat(60, 0.0), 1.0, lambda s, d: "never shown")

    assert describe_window([weak, silent, strong], 0, 30) == "strong evidence; weak evidence"
