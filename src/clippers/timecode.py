"""Parse human-friendly timestamps ("83", "1:23", "1:02:03.5") into seconds."""

import math

_MAX_PARTS = 3  # HH:MM:SS


def parse_timestamp(value: str) -> float:
    """Convert "SS", "MM:SS" or "HH:MM:SS" (fractional seconds allowed) to seconds.

    Raises:
        ValueError: if the string is not a valid, non-negative timestamp.
    """
    parts = value.strip().split(":")
    if len(parts) > _MAX_PARTS:
        raise ValueError(f"invalid timestamp: {value!r} (expected SS, MM:SS or HH:MM:SS)")

    try:
        numbers = [float(part) for part in parts]
    except ValueError as e:
        raise ValueError(f"invalid timestamp: {value!r}") from e

    if not all(math.isfinite(n) and n >= 0 for n in numbers):
        raise ValueError(f"invalid timestamp: {value!r} (must be a finite, non-negative number)")

    *larger_units, _seconds = numbers
    if any(not n.is_integer() for n in larger_units):
        raise ValueError(f"invalid timestamp: {value!r} (only seconds may be fractional)")
    if any(n >= 60 for n in numbers[1:]):
        raise ValueError(f"invalid timestamp: {value!r} (minutes and seconds must be < 60)")

    total = 0.0
    for n in numbers:
        total = total * 60 + n
    return total


def format_timestamp(seconds: float) -> str:
    """Seconds -> "M:SS" or "H:MM:SS" (whole seconds). The inverse of parse_timestamp."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"
