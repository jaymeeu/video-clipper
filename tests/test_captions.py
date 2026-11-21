import pytest
from pydantic import ValidationError

from clippers.captions import ass_time, build_ass, chunk_words
from clippers.transcribe import Transcript, Word


def words_from(
    spec: str, *, step: float = 0.4, gap_after: dict[int, float] | None = None
) -> list[Word]:
    """Build evenly timed words from a sentence; `gap_after` inserts pauses after word i."""
    gaps = gap_after or {}
    words: list[Word] = []
    t = 0.0
    for i, text in enumerate(spec.split()):
        words.append(Word(text=text, start=t, end=t + step * 0.8, probability=0.9))
        t += step + gaps.get(i, 0.0)
    return words


def texts(chunks: list[list[Word]]) -> list[str]:
    return [" ".join(w.text for w in chunk) for chunk in chunks]


class TestChunkWords:
    def test_splits_at_max_words(self) -> None:
        chunks = chunk_words(words_from("we dey here no shaking at all"), max_chars=100)
        assert texts(chunks) == ["we dey here", "no shaking at", "all"]

    def test_splits_at_max_chars(self) -> None:
        chunks = chunk_words(words_from("unbelievable performance tonight"), max_chars=20)
        assert texts(chunks) == ["unbelievable", "performance tonight"]

    def test_splits_on_pause(self) -> None:
        chunks = chunk_words(words_from("wait for it boom", gap_after={2: 1.0}))
        assert texts(chunks) == ["wait for it", "boom"]

    def test_splits_after_sentence_end(self) -> None:
        chunks = chunk_words(words_from("Gift! Thank you"))
        assert texts(chunks) == ["Gift!", "Thank you"]

    def test_empty(self) -> None:
        assert chunk_words([]) == []


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00:00.00"), (1.234, "0:00:01.23"), (61.5, "0:01:01.50"), (3725.999, "1:02:06.00")],
)
def test_ass_time(seconds: float, expected: str) -> None:
    assert ass_time(seconds) == expected


class TestBuildAss:
    def test_one_event_per_word_with_active_word_highlighted(self) -> None:
        ass = build_ass(words_from("na wa o"))
        events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

        assert len(events) == 3
        assert r"{\c&H0000FFFF&\fscx110\fscy110}na{\r} wa o" in events[0]
        assert r"na {\c&H0000FFFF&\fscx110\fscy110}wa{\r} o" in events[1]

    def test_events_are_continuous_within_a_chunk(self) -> None:
        ass = build_ass(words_from("one two three", step=0.5))
        events = [line.split(",") for line in ass.splitlines() if line.startswith("Dialogue:")]

        ends = [e[2] for e in events[:-1]]
        next_starts = [e[1] for e in events[1:]]
        assert ends == next_starts  # no flicker between words

    def test_markup_in_speech_is_escaped(self) -> None:
        ass = build_ass([Word(text="{evil}\\N", start=0, end=0.5, probability=1)])

        assert "(evil)/N" in ass

    def test_header_matches_vertical_output(self) -> None:
        ass = build_ass([])

        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass


class TestModels:
    def test_transcript_round_trips_through_json(self) -> None:
        transcript = Transcript(
            language="en", language_probability=0.97, words=words_from("we move")
        )

        restored = Transcript.model_validate_json(transcript.model_dump_json())

        assert restored == transcript
        assert restored.text == "we move"

    def test_word_rejects_negative_time(self) -> None:
        with pytest.raises(ValidationError):
            Word(text="x", start=-1, end=0.5, probability=0.5)

    def test_word_is_immutable(self) -> None:
        word = Word(text="x", start=0, end=0.5, probability=0.5)
        with pytest.raises(ValidationError):
            word.text = "y"  # type: ignore[misc]
