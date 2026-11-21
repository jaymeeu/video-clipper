"""Turn timed words into an ASS subtitle file with TikTok-style word highlighting.

ASS (Advanced SubStation Alpha) is the subtitle format ffmpeg's libass renders. Unlike SRT
it supports fonts, outlines, positioning and per-word colour changes.
"""

from collections.abc import Sequence
from pathlib import Path

from clippers.framing import OUTPUT_HEIGHT, OUTPUT_WIDTH
from clippers.transcribe import Word

MAX_WORDS_PER_CHUNK = 3
MAX_CHARS_PER_CHUNK = 20
MAX_GAP = 0.6  # a pause longer than this (seconds) starts a new chunk
HOLD = 0.3  # keep the last chunk of a phrase on screen this long after it's spoken
_SENTENCE_END = (".", "?", "!")

# ASS colours are &HAABBGGRR: alpha, then blue-green-red (reversed from CSS's RGB).
_WHITE = "&H00FFFFFF"
_YELLOW = "&H0000FFFF"
_BLACK = "&H00000000"
_SHADOW = "&H80000000"  # 50% transparent black

_HEADER = f"""\
[Script Info]
ScriptType: v4.00+
PlayResX: {OUTPUT_WIDTH}
PlayResY: {OUTPUT_HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, \
Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, \
Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,84,{_WHITE},{_WHITE},{_BLACK},{_SHADOW},\
-1,0,0,0,100,100,0,0,1,6,3,2,80,80,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def chunk_words(
    words: Sequence[Word],
    *,
    max_words: int = MAX_WORDS_PER_CHUNK,
    max_chars: int = MAX_CHARS_PER_CHUNK,
    max_gap: float = MAX_GAP,
) -> list[list[Word]]:
    """Group words into short on-screen chunks.

    A new chunk starts when the current one is full (word or character limit), when the
    speaker pauses, or after the end of a sentence.
    """
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current:
            too_many = len(current) >= max_words
            too_long = len(" ".join(w.text for w in [*current, word])) > max_chars
            paused = word.start - current[-1].end > max_gap
            if too_many or too_long or paused:
                chunks.append(current)
                current = []
        current.append(word)
        if word.text.endswith(_SENTENCE_END):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def ass_time(seconds: float) -> str:
    """Format seconds as ASS time: H:MM:SS.cc (centiseconds)."""
    centis = max(0, round(seconds * 100))
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def _escape(text: str) -> str:
    """Neutralise characters ASS treats as markup in dialogue text."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def _highlighted(chunk: Sequence[Word], active: int) -> str:
    parts: list[str] = []
    for i, word in enumerate(chunk):
        text = _escape(word.text)
        if i == active:
            # Yellow and 10% bigger, then \r resets to the default style.
            text = rf"{{\c{_YELLOW}&\fscx110\fscy110}}{text}{{\r}}"
        parts.append(text)
    return " ".join(parts)


def build_ass(words: Sequence[Word]) -> str:
    """Render words as a complete ASS document.

    Each chunk is shown as one line of text; while each word is spoken it's highlighted,
    so there is one dialogue event per word.
    """
    chunks = chunk_words(words)
    lines = [_HEADER]
    for i, chunk in enumerate(chunks):
        next_start = chunks[i + 1][0].start if i + 1 < len(chunks) else float("inf")
        chunk_end = min(chunk[-1].end + HOLD, next_start)
        for j, word in enumerate(chunk):
            start = word.start
            end = chunk[j + 1].start if j + 1 < len(chunk) else chunk_end
            if end <= start:
                continue  # zero-length word from Whisper: nothing to show
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,"
                f"{_highlighted(chunk, j)}\n"
            )
    return "".join(lines)


def write_ass(words: Sequence[Word], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(words), encoding="utf-8")
    return path
