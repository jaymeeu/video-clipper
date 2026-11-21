"""Ask a language model which transcript moments would make good short clips.

The rest of clippers only sees `MomentSuggester` (an interface) and `AIMoment` (our own
validated model), so swapping OpenAI for another provider means writing one class.
Results are cached: re-running detect on the same transcript doesn't pay twice.
"""

import logging
import os
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from clippers import cache
from clippers.transcribe import Transcript, Word

logger = logging.getLogger(__name__)

FALLBACK_AI_MODEL = "gpt-5-mini"
PROMPT_VERSION = "1"  # bump when the prompt changes, so old cached answers aren't reused
MAX_WORDS_PER_REQUEST = 8_000  # ~11k tokens of transcript: long streams are split up

INSTRUCTIONS = """\
You pick highlight moments from transcripts of livestreams and videos, to be cut into
15-60 second vertical clips for TikTok, Reels and Shorts.

The speakers may be Nigerian and switch between English and Nigerian Pidgin; treat Pidgin
as normal speech and understand its humour and slang. The transcript is machine-made and
may contain mistakes, especially in Pidgin.

Good moments stand on their own without context: jokes and punchlines, roasts and banter,
surprising or controversial statements, strong emotion, wins and losses, big reactions
to gifts or the audience, quotable lines, and the payoff of a story. Avoid greetings,
"follow/subscribe" requests, technical setup, and dead air.

Each transcript line starts with its time in seconds, like [83.4]. For every moment give:
- start and end in seconds, taken from the line times; include a little build-up before
  the payoff, and keep it between 15 and 60 seconds long
- a short, punchy title (max 8 words) in the speakers' own style
- one sentence on why it works as a clip
- a score from 1 (weak) to 10 (would go viral)
Return fewer moments rather than weak ones. Return an empty list if nothing qualifies."""


class AIMoment(BaseModel):
    """A suggestion that passed our own checks (times in seconds, score 1-10)."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(max_length=120)
    reason: str = Field(max_length=500)
    score: int = Field(ge=1, le=10)


class AIMoments(BaseModel):
    """What gets cached."""

    moments: list[AIMoment]


class Suggestion(BaseModel):
    """The shape we ask the model to return. Plain types only: providers' structured-output
    modes support a limited JSON Schema, so the range checks happen afterwards, in our code."""

    start: float
    end: float
    title: str
    reason: str
    score: int


class Suggestions(BaseModel):
    moments: list[Suggestion]


def default_ai_model() -> str:
    """CLIPPERS_AI_MODEL if set, else the fallback.

    Read at call time, not import time: a .env file is loaded after modules are
    imported, so a module-level constant would silently ignore it.
    """
    return os.environ.get("CLIPPERS_AI_MODEL") or FALLBACK_AI_MODEL


class AIScoringError(RuntimeError):
    """The AI provider couldn't be reached or didn't return a usable answer."""


class MomentSuggester(Protocol):
    """Anything that can read transcript text and suggest moments."""

    @property
    def model(self) -> str: ...

    def suggest(self, transcript_text: str, *, max_moments: int) -> Suggestions: ...


class OpenAISuggester:
    """MomentSuggester backed by the OpenAI Responses API with structured output."""

    def __init__(self, model: str | None = None) -> None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise AIScoringError(
                "OPENAI_API_KEY is not set. Add `export OPENAI_API_KEY=...` to your shell "
                "profile (never to this repo), or run detect without --ai."
            )
        import openai  # deferred: only needed when AI scoring is actually used

        self._model = model or default_ai_model()
        self._client = openai.OpenAI()

    @property
    def model(self) -> str:
        return self._model

    def suggest(self, transcript_text: str, *, max_moments: int) -> Suggestions:
        import openai

        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=INSTRUCTIONS,
                input=f"Return up to {max_moments} moments.\n\nTRANSCRIPT:\n{transcript_text}",
                text_format=Suggestions,
            )
        except openai.OpenAIError as e:
            raise AIScoringError(f"OpenAI request failed: {e}") from e

        if response.usage is not None:
            logger.info(
                "AI request used %d input + %d output tokens",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
        if response.output_parsed is None:
            raise AIScoringError("the model returned no usable answer (refused or cut off)")
        return response.output_parsed


def transcript_lines(words: Sequence[Word]) -> list[str]:
    """Group words into short timestamped lines: '[83.4] text...'.

    A new line starts at a pause, after a sentence end, or when a line gets long, so the
    model sees natural phrases and can quote accurate times.
    """
    lines: list[str] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            lines.append(f"[{current[0].start:.1f}] " + " ".join(w.text for w in current))
            current.clear()

    for word in words:
        if current and (
            word.start - current[-1].end > 1.0
            or len(current) >= 25
            or (len(current) >= 6 and current[-1].text.endswith((".", "?", "!")))
        ):
            flush()
        current.append(word)
    flush()
    return lines


def chunk_lines(lines: Sequence[str], max_words: int = MAX_WORDS_PER_REQUEST) -> list[list[str]]:
    """Split lines into request-sized chunks of at most ~`max_words` words."""
    chunks: list[list[str]] = []
    current: list[str] = []
    words = 0
    for line in lines:
        line_words = len(line.split())
        if current and words + line_words > max_words:
            chunks.append(current)
            current, words = [], 0
        current.append(line)
        words += line_words
    if current:
        chunks.append(current)
    return chunks


def _validated(suggestions: Suggestions, video_seconds: float) -> list[AIMoment]:
    """Keep suggestions that make sense; fix what can be fixed (clamp times and scores)."""
    moments: list[AIMoment] = []
    for s in suggestions.moments:
        start, end = max(0.0, s.start), min(s.end, video_seconds)
        if end - start < 3:  # nonsense or empty after clamping
            logger.debug("dropping AI suggestion with bad times: %s", s)
            continue
        moments.append(
            AIMoment(
                start=start,
                end=end,
                title=s.title.strip()[:120],
                reason=s.reason.strip()[:500],
                score=min(10, max(1, s.score)),
            )
        )
    return moments


def suggest_moments(
    transcript: Transcript, suggester: MomentSuggester, *, max_moments: int
) -> list[AIMoment]:
    """AI-suggested moments for a whole transcript, cached per transcript + model + prompt."""
    lines = transcript_lines(transcript.words)
    if not lines:
        return []
    text = "\n".join(lines)
    path = cache.cache_path("ai", suggester.model, PROMPT_VERSION, str(max_moments), text)
    if (cached := cache.load(path, AIMoments)) is not None:
        logger.info("using cached AI suggestions (%d moments)", len(cached.moments))
        return cached.moments

    chunks = chunk_lines(lines)
    logger.info("asking %s for moments (%d request(s))", suggester.model, len(chunks))
    video_seconds = transcript.words[-1].end
    moments: list[AIMoment] = []
    for chunk in chunks:
        suggestions = suggester.suggest("\n".join(chunk), max_moments=max_moments)
        moments += _validated(suggestions, video_seconds)

    cache.save(path, AIMoments(moments=moments))
    return moments
