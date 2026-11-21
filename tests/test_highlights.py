import numpy as np
import pytest

from clippers.highlights import above_baseline, find_highlights, pick_windows, window_scores
from clippers.timecode import format_timestamp


def stream(seconds: int, base_db: float = -30.0, **bursts: tuple[int, int, float]) -> np.ndarray:
    """A flat loudness track with bursts: name=(start, end, dB above base)."""
    loudness = np.full(seconds, base_db)
    for start, end, boost in bursts.values():
        loudness[start:end] += boost
    return loudness


class TestAboveBaseline:
    def test_flat_signal_is_never_above_baseline(self) -> None:
        assert np.allclose(above_baseline(stream(300)), 0)

    def test_burst_stands_out_by_its_boost(self) -> None:
        result = above_baseline(stream(300, shout=(100, 105, 20)))

        assert result[102] == pytest.approx(20)
        assert result[50] == pytest.approx(0)

    def test_relative_to_local_baseline(self) -> None:
        # Loud music section from 300s; a +5 dB shout inside it still stands out,
        # while the music itself (once it's "normal" for that stretch) does not.
        loudness = stream(600, music=(300, 600, 15), shout=(450, 453, 5))

        result = above_baseline(loudness)

        assert result[451] == pytest.approx(5)
        assert result[550] == pytest.approx(0)

    def test_silent_first_second_does_not_inflate_the_opening(self) -> None:
        # Regression: edge padding copied the silent first second 60 times into the
        # baseline. On real (varying) audio that drags the median down, so an ordinary
        # opening scored ~2x as "exciting" as an equally ordinary middle section.
        rng = np.random.default_rng(seed=0)  # seeded: same "random" audio every run
        loudness = -30 + rng.normal(0, 3, 300)
        loudness[0] = -90

        result = above_baseline(loudness)

        assert result[1:30].mean() <= result[120:150].mean() * 1.25

    def test_quieter_than_usual_is_not_negative(self) -> None:
        assert above_baseline(stream(300, lull=(100, 120, -20))).min() == 0

    def test_empty(self) -> None:
        assert above_baseline(np.array([])).size == 0


class TestWindowScores:
    def test_one_score_per_possible_start(self) -> None:
        assert window_scores(np.zeros(100), 30).size == 71

    def test_burst_is_centred_in_best_window(self) -> None:
        signal = np.zeros(200)
        signal[100:110] = 10  # burst centre = 105

        best_start = int(np.argmax(window_scores(signal, 30)))

        assert best_start + 15 == pytest.approx(105, abs=1)

    def test_short_signal_gives_single_window(self) -> None:
        assert window_scores(np.array([1.0, 3.0]), 30).tolist() == [2.0]


class TestPickWindows:
    def test_best_first_and_never_overlapping(self) -> None:
        scores = np.zeros(100)
        scores[10], scores[20], scores[60] = 5, 9, 7  # 10 overlaps 20 at duration 30

        picks = pick_windows(scores, duration=30, count=5)

        assert [start for start, _ in picks] == [20, 60]

    def test_respects_count(self) -> None:
        scores = np.zeros(500)
        scores[::50] = 5

        assert len(pick_windows(scores, duration=30, count=3)) == 3

    def test_ignores_scores_below_minimum(self) -> None:
        assert pick_windows(np.full(100, 0.05), duration=30, count=5) == []


def test_find_highlights_end_to_end_on_arrays() -> None:
    loudness = stream(900, big=(600, 610, 25), small=(200, 205, 12))
    strength = above_baseline(loudness) / 10  # loudness in strength units (10 dB = 1.0)

    moments = find_highlights(strength, count=5, duration=30)

    assert len(moments) == 2  # nothing else stands out: fewer picks, no filler
    assert moments[0].score > moments[1].score
    assert moments[0].start <= 600 and moments[0].start + 30 >= 610  # contains the burst
    assert moments[1].start <= 200 and moments[1].start + 30 >= 205


@pytest.mark.parametrize(
    ("seconds", "expected"), [(0, "0:00"), (65, "1:05"), (725.9, "12:05"), (3725, "1:02:05")]
)
def test_format_timestamp(seconds: float, expected: str) -> None:
    assert format_timestamp(seconds) == expected
