"""The moments file: which parts of a video to clip.

Written by hand today, and by the highlight detector in Phase 2. Example:

    {
      "source": "https://www.youtube.com/watch?v=...",
      "moments": [
        {"start": "1:23", "duration": 30, "title": "the robot hand reveal"},
        {"start": 250, "duration": 20}
      ]
    }
"""

from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from clippers.framing import Framing
from clippers.timecode import parse_timestamp


def _to_seconds(value: Any) -> Any:
    """Accept "1:23"-style strings as well as plain numbers."""
    if isinstance(value, str):
        return parse_timestamp(value)  # its ValueError becomes a pydantic validation error
    return value


Seconds = Annotated[float, BeforeValidator(_to_seconds), Field(ge=0)]


class Moment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: Seconds
    duration: float = Field(default=30.0, gt=0, le=600)
    title: str | None = Field(default=None, max_length=200)
    # Filled in by the highlight detector; optional for hand-written files.
    score: float | None = None  # higher = stronger highlight; only comparable within one file
    reason: str | None = Field(default=None, max_length=500)  # why it was picked


class MomentsFile(BaseModel):
    # extra="forbid": a typo like "strat" or "captons" is an error, not silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, description="http(s) URL, or a path relative to the file")
    moments: list[Moment] = Field(min_length=1)
    framing: Framing = Framing.BLUR
    captions: bool = True


class MomentsFileError(ValueError):
    """A moments file couldn't be read or failed validation. The message lists every problem."""


def load_moments(path: Path) -> MomentsFile:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as e:
        raise MomentsFileError(f"moments file not found: {path}") from e
    try:
        return MomentsFile.model_validate_json(raw)
    except ValidationError as e:
        raise MomentsFileError(format_validation_error(path, e)) from e


def save_moments(plan: MomentsFile, path: Path) -> Path:
    """Write `plan` as pretty JSON, leaving out unset optional fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")
    return path


def format_validation_error(path: Path, error: ValidationError) -> str:
    """One readable line per problem, e.g. `moments[2].start: invalid timestamp: '1:60'`."""
    lines = [f"{path}: {error.error_count()} problem(s)"]
    for problem in error.errors():
        where = "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in problem["loc"]
        ).lstrip(".")
        message = problem["msg"].removeprefix("Value error, ")
        lines.append(f"  {where or '(file)'}: {message}")
    return "\n".join(lines)
