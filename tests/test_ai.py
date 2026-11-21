from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from clippers.ai import (
    AIScoringError,
    OpenAISuggester,
    Suggestion,
    Suggestions,
    chunk_lines,
    suggest_moments,
    transcript_lines,
)
from clippers.transcribe import Transcript, Word


def words(*timed: tuple[float, str]) -> list[Word]:
    return [Word(text=t, start=s, end=s + 0.3, probability=0.9) for s, t in timed]


def transcript(*timed: tuple[float, str]) -> Transcript:
    return Transcript(language="en", language_probability=0.9, words=words(*timed))


class FakeSuggester:
    """Implements MomentSuggester without any network: returns canned suggestions."""

    def __init__(self, *suggestions: Suggestion, model: str = "fake-model") -> None:
        self._suggestions = list(suggestions)
        self._model = model
        self.requests: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    def suggest(self, transcript_text: str, *, max_moments: int) -> Suggestions:
        self.requests.append(transcript_text)
        return Suggestions(moments=self._suggestions)


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLIPPERS_CACHE_DIR", str(tmp_path / "cache"))


class TestTranscriptLines:
    def test_lines_break_at_pauses_and_carry_start_times(self) -> None:
        lines = transcript_lines(words((1.0, "we"), (1.4, "move"), (5.0, "omo"), (5.4, "see")))

        assert lines == ["[1.0] we move", "[5.0] omo see"]

    def test_lines_break_after_sentences_once_long_enough(self) -> None:
        said = [
            (i * 0.4, w)
            for i, w in enumerate(["one", "two", "three", "four", "five", "six.", "seven"])
        ]

        assert transcript_lines(words(*said)) == [
            "[0.0] one two three four five six.",
            "[2.4] seven",
        ]

    def test_chunks_respect_word_budget(self) -> None:
        lines = ["[0.0] a b c", "[1.0] d e f", "[2.0] g h i"]

        assert chunk_lines(lines, max_words=8) == [lines[:2], lines[2:]]


class TestSuggestMoments:
    def test_validates_and_clamps_suggestions(self) -> None:
        t = transcript((0, "hello"), (99.7, "bye"))  # video ends at ~100s
        suggester = FakeSuggester(
            Suggestion(start=10, end=40, title=" Chai! ", reason="big reaction", score=14),
            Suggestion(start=90, end=500, title="end", reason="runs past end", score=5),
            Suggestion(start=50, end=50, title="empty", reason="zero length", score=9),
        )

        moments = suggest_moments(t, suggester, max_moments=5)

        assert [(m.start, m.end, m.title, m.score) for m in moments] == [
            (10, 40, "Chai!", 10),  # score clamped to 10, title trimmed
            (90, 100.0, "end", 5),  # end clamped to the video
        ]  # the zero-length one is dropped

    def test_results_are_cached_per_model(self) -> None:
        t = transcript((0, "hello"), (5, "world"))
        good = Suggestion(start=0, end=5, title="t", reason="r", score=6)
        first, second = FakeSuggester(good), FakeSuggester(good)
        other_model = FakeSuggester(good, model="another-model")

        suggest_moments(t, first, max_moments=5)
        suggest_moments(t, second, max_moments=5)
        suggest_moments(t, other_model, max_moments=5)

        assert len(first.requests) == 1
        assert second.requests == []  # served from cache: no second charge
        assert len(other_model.requests) == 1

    def test_empty_transcript_makes_no_request(self) -> None:
        suggester = FakeSuggester()

        assert suggest_moments(transcript(), suggester, max_moments=5) == []
        assert suggester.requests == []


class TestOpenAISuggester:
    def test_missing_key_is_a_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(AIScoringError, match="OPENAI_API_KEY is not set"):
            OpenAISuggester()

    def _with_fake_client(self, monkeypatch: pytest.MonkeyPatch, parse: Any) -> OpenAISuggester:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        suggester = OpenAISuggester("gpt-test")
        suggester._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))  # pyright: ignore[reportAttributeAccessIssue,reportPrivateUsage]
        return suggester

    def test_returns_parsed_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answer = Suggestions(moments=[Suggestion(start=1, end=20, title="t", reason="r", score=7)])
        seen: dict[str, Any] = {}

        def parse(**kwargs: Any) -> SimpleNamespace:
            seen.update(kwargs)
            usage = SimpleNamespace(input_tokens=100, output_tokens=20)
            return SimpleNamespace(output_parsed=answer, usage=usage)

        result = self._with_fake_client(monkeypatch, parse).suggest("[1.0] hi", max_moments=3)

        assert result == answer
        assert seen["model"] == "gpt-test"
        assert seen["text_format"] is Suggestions
        assert "Return up to 3 moments" in seen["input"]

    def test_api_failure_becomes_scoring_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def parse(**_: Any) -> None:
            raise openai.OpenAIError("connection reset")  # base class of all SDK errors

        suggester = self._with_fake_client(monkeypatch, parse)

        with pytest.raises(AIScoringError, match="OpenAI request failed"):
            suggester.suggest("[1.0] hi", max_moments=3)

    def test_refusal_becomes_scoring_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def parse(**_: Any) -> SimpleNamespace:
            return SimpleNamespace(output_parsed=None, usage=None)

        suggester = self._with_fake_client(monkeypatch, parse)

        with pytest.raises(AIScoringError, match="no usable answer"):
            suggester.suggest("[1.0] hi", max_moments=3)
