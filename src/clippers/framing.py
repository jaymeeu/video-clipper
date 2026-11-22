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

# In blur mode, the sharp centre video is at least this share of the frame's height.
# A 16:9 source fitted to the width is only ~32% tall, which looks small on a phone; at
# 0.6 it's zoomed in and its sides are trimmed (you see the middle ~53% of the width).
FOREGROUND_HEIGHT = 0.6


class Framing(StrEnum):
    """How to fit the source into the output frame."""

    ORIGINAL = "original"  # keep the source size and aspect ratio
    CROP = "crop"  # fill 9:16 and centre-crop the overflow (cuts the sides of landscape video)
    BLUR = "blur"  # sharp centre video (>= 3/5 of the height) over a blurred copy of itself


def foreground_chain(
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
    min_height_ratio: float = FOREGROUND_HEIGHT,
) -> str:
    """The sharp centre video of blur mode, as an ffmpeg filter chain.

    Its height is the larger of (a) `min_height_ratio` of the frame and (b) the height it
    has when fitted to the frame. So landscape and square sources are zoomed in and
    centre-cropped to the frame width, while vertical sources stay whole (they're
    already taller than the minimum). Heights are kept even, as H.264 requires.
    """
    min_h = round(height * min_height_ratio / 2) * 2
    fitted_h = f"trunc(min({height}\\,{width}*ih/iw)/2)*2"  # height when fitted, even
    # `\\,` in this source = `\,` in the string: an escaped comma inside an ffmpeg
    # expression (a bare comma would end the filter).
    return f"scale=w=-2:h=max({min_h}\\,{fitted_h}),crop=w=min(iw\\,{width}):h=ih"


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
                f"[fg]{foreground_chain(width, height)}[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )
        case _:
            assert_never(framing)
