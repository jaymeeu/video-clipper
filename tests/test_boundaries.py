import pytest

from clippers.ai import AIMoment
from clippers.boundaries import LEAD_IN, TAIL, breaks, snap_span
from clippers.detect import MAX_CLIP, MIN_CLIP, refine
from clippers.highlights import Highlight
from clippers.transcribe import Transcript, Word


def said(*timed: tuple[float, str]) -> list[Word]:
    """Words from (start, text), each 0.3s long."""
    return [Word(text=t, start=s, end=s + 0.3, probability=0.9) for s, t in timed]


# Two sentences: "Look Celia, we move." (10.0-11.5) then a pause, "Another line here." (13-14.1)
TALK = said(
    (10.0, "Look"), (10.4, "Celia,"), (10.8, "we"), (11.2, "move."),
    (13.0, "Another"), (13.4, "line"), (13.8, "here."),
)  # fmt: skip


class TestBreaks:
    def test_breaks_at_sentence_ends_and_pauses(self) -> None:
        starts, ends = breaks(TALK)

        assert starts == [10.0, 13.0]
        assert ends == pytest.approx([11.5, 14.1])

    def test_no_words(self) -> None:
        assert breaks([]) == ([], [])


class TestSnapSpan:
    def test_start_mid_phrase_moves_back_to_phrase_start(self) -> None:
        start, _ = snap_span(10.9, 30, TALK, video_seconds=60)

        assert start == pytest.approx(10.0 - LEAD_IN)

    def test_end_mid_phrase_moves_forward_to_phrase_end(self) -> None:
        _, end = snap_span(0, 13.5, TALK, video_seconds=60)

        assert end == pytest.approx(14.1 + TAIL)

    def test_end_exactly_at_next_phrase_start_does_not_pull_it_in(self) -> None:
        # Regression from a real run: the AI ended a moment at 356.8s, exactly where the
        # next line began; snapping stretched the clip to finish that next line.
        _, end = snap_span(0, 13.0, TALK, video_seconds=60)  # 13.0 = "Another" starts

        assert end == 13.0

    def test_edges_in_a_pause_stay_put(self) -> None:
        assert snap_span(12.2, 12.8, TALK, video_seconds=60) == (12.2, 12.8)

    def test_never_shifts_further_than_max(self) -> None:
        long_phrase = said(*[(i * 0.4, "word") for i in range(50)])  # 20s with no break

        assert snap_span(15.0, 30, long_phrase, video_seconds=60, max_shift=4)[0] == 15.0

    def test_clamped_to_the_video(self) -> None:
        start, end = snap_span(10.1, 14.0, TALK, video_seconds=14.2)

        assert start >= 0 and end == 14.2

    def test_no_words_changes_nothing(self) -> None:
        assert snap_span(3.0, 9.0, [], video_seconds=60) == (3.0, 9.0)


def pick(start: int, score: float, duration: int = 30) -> Highlight:
    return Highlight(start=start, duration=duration, score=score)


def ai(start: float, end: float, title: str, score: int = 8) -> AIMoment:
    return AIMoment(start=start, end=end, title=title, reason="r", score=score)


class TestRefine:
    def test_one_ai_moment_split_across_picks_becomes_one_clip(self) -> None:
        # Regression from a real run: 30s windows at 372s and 402s both landed on one
        # 43s AI moment (379-422s), giving two clips of the same scene with one title.
        moments = [ai(379.1, 422.3, "You Forgot Me On Earth!")]

        spans = refine(
            [pick(372, 3.2), pick(402, 1.9), pick(100, 1.5)],
            count=5, video_seconds=735, ai_moments=moments,
        )  # fmt: skip

        assert [(s.start, s.end, s.ai and s.ai.title) for s in spans] == [
            (379.1, 422.3, "You Forgot Me On Earth!"),
            (100.0, 130.0, None),
        ]

    def test_dropped_duplicates_are_replaced_by_later_candidates(self) -> None:
        spans = refine(
            [pick(0, 5), pick(10, 4), pick(200, 3), pick(400, 2)],  # 0 and 10 overlap
            count=3, video_seconds=600,
        )  # fmt: skip

        assert [s.start for s in spans] == [0, 200, 400]

    def test_passing_overlap_does_not_borrow_ai_title(self) -> None:
        moments = [ai(25, 60, "Mostly elsewhere")]  # 5s of overlap with a 30s window

        [span] = refine([pick(0, 2)], count=1, video_seconds=600, ai_moments=moments)

        assert (span.start, span.end, span.ai) == (0, 30, None)

    def test_ai_span_is_kept_within_length_limits(self) -> None:
        moments = [ai(100, 300, "Too long"), ai(500, 503, "Too short")]

        spans = refine(
            [pick(150, 3), pick(487, 2, duration=20)],
            count=2, video_seconds=600, ai_moments=moments,
        )  # fmt: skip

        assert spans[0].duration == MAX_CLIP
        assert spans[1].duration == MIN_CLIP

    def test_edges_snap_to_phrases(self) -> None:
        [span] = refine([pick(11, 2, duration=10)], count=1, video_seconds=60, words=TALK)

        assert span.start == pytest.approx(10.0 - LEAD_IN)  # "Look Celia..." not "...move."


def test_transcript_between_retimes_words_to_the_clip() -> None:
    transcript = Transcript(language="en", language_probability=0.9, words=TALK)

    clip = transcript.between(10.5, 13.6)

    assert [(w.text, round(w.start, 2)) for w in clip.words] == [
        ("we", 0.3), ("move.", 0.7), ("Another", 2.5), ("line", 2.9),
    ]  # fmt: skip
    assert clip.words[-1].end == pytest.approx(13.6 - 10.5)  # cut at the clip's end
