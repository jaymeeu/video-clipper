"""Fit any source video into a vertical 9:16 frame, as ffmpeg filter graphs.

Pure string builders: no I/O, so they're trivial to test and reuse.
"""

from enum import StrEnum
from typing import assert_never

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

# The blurred background is built at 1/4 resolution and scaled up: it's going to be a
# blur anyway, and blurring 16x fewer pixels is much faster on CPU.
_BG_DOWNSCALE = 4


class Framing(StrEnum):
    """How to fit the source into the output frame."""

    ORIGINAL = "original"  # keep the source size and aspect ratio
    CROP = "crop"  # fill 9:16 and centre-crop the overflow (cuts the sides of landscape video)
    BLUR = "blur"  # fit the whole frame, fill the bars with a blurred, zoomed copy of itself


def framing_filter(
    framing: Framing, width: int = OUTPUT_WIDTH, height: int = OUTPUT_HEIGHT
) -> str | None:
    """Return the ffmpeg `-vf` filter graph for `framing`, or None if no filtering is needed.

    Works for any input aspect ratio: landscape, portrait (already 9:16) or square.
    """
    match framing:
        case Framing.ORIGINAL:
            return None
        case Framing.CROP:
            return (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1"
            )
        case Framing.BLUR:
            bg_w, bg_h = width // _BG_DOWNSCALE, height // _BG_DOWNSCALE
            return (
                "split=2[bg][fg];"
                f"[bg]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,"
                f"crop={bg_w}:{bg_h},boxblur=10:2,scale={width}:{height}[bg];"
                f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease"
                ":force_divisible_by=2[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )
        case _:
            assert_never(framing)
