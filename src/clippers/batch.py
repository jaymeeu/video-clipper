"""Render every moment in a moments file into its own clip."""

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from clippers.moments import Moment, MomentsFile
from clippers.pipeline import CaptionOptions, make_clip
from clippers.transcribe import Transcript
from clippers.video import FFmpegError

logger = logging.getLogger(__name__)

# Failures that belong to one clip (bad range, broken input, ffmpeg error). Anything else
# is a bug in our code and should stop the run loudly, not be recorded and skipped.
_CLIP_ERRORS = (ValueError, FileNotFoundError, FFmpegError)


@dataclass(frozen=True, slots=True)
class ClipOutcome:
    number: int  # 1-based, matches the filename prefix
    moment: Moment
    path: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def slugify(text: str, max_length: int = 50) -> str:
    """'Ọmọ dey vibe! 🔥' -> 'omo-dey-vibe'. Safe for filenames on every OS."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")


def clip_filename(number: int, moment: Moment) -> str:
    """'03-robot-hand-reveal.mp4', or '03-1m23s.mp4' when the moment has no title."""
    label = slugify(moment.title) if moment.title else ""
    if not label:
        minutes, seconds = divmod(int(moment.start), 60)
        label = f"{minutes}m{seconds:02}s"
    return f"{number:02}-{label}.mp4"


def run_batch(
    plan: MomentsFile,
    source: Path,
    output_dir: Path,
    *,
    captions: CaptionOptions | None,
    transcript: Transcript | None = None,
) -> list[ClipOutcome]:
    """Make one clip per moment. A failing clip is recorded and the batch carries on.

    With a whole-video `transcript`, captions are cut from it instead of transcribing
    each clip again.
    """
    outcomes: list[ClipOutcome] = []
    total = len(plan.moments)
    for number, moment in enumerate(plan.moments, start=1):
        output = output_dir / clip_filename(number, moment)
        logger.info("[%d/%d] %s", number, total, output.name)
        try:
            result = make_clip(
                source,
                output,
                start=moment.start,
                duration=moment.duration,
                framing=plan.framing,
                captions=captions,
                transcript=transcript,
            )
        except _CLIP_ERRORS as e:
            logger.error("[%d/%d] failed: %s", number, total, e)
            outcomes.append(ClipOutcome(number=number, moment=moment, error=str(e)))
        else:
            outcomes.append(ClipOutcome(number=number, moment=moment, path=result.path))
    return outcomes
