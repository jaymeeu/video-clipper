import subprocess
from pathlib import Path

import pytest

from clippers.framing import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    Framing,
    foreground_chain,
    framing_filter,
)
from clippers.video import cut_clip
from tests.media import MakeVideo, probe_size, requires_ffmpeg

# Real-world source shapes: 16:9 HD, an odd-height laptop capture, a phone stream
# that is already vertical, and 4:3.
SOURCE_SIZES = [(1280, 720), (1366, 768), (720, 1280), (320, 240)]


def test_original_needs_no_filter() -> None:
    assert framing_filter(Framing.ORIGINAL) is None


@pytest.mark.parametrize("framing", [f for f in Framing if f is not Framing.ORIGINAL])
def test_reframing_modes_produce_a_filter(framing: Framing) -> None:
    assert framing_filter(framing)


@requires_ffmpeg
@pytest.mark.parametrize("framing", [Framing.CROP, Framing.BLUR])
@pytest.mark.parametrize(("src_w", "src_h"), SOURCE_SIZES)
def test_vertical_framing_outputs_1080x1920(
    make_video: MakeVideo, tmp_path: Path, framing: Framing, src_w: int, src_h: int
) -> None:
    source = make_video(src_w, src_h, seconds=1.0)
    out = tmp_path / "clip.mp4"

    cut_clip(source, out, start=0.0, duration=0.5, framing=framing)

    assert probe_size(out) == (OUTPUT_WIDTH, OUTPUT_HEIGHT)


@requires_ffmpeg
def test_original_framing_keeps_source_size(make_video: MakeVideo, tmp_path: Path) -> None:
    source = make_video(1280, 720, seconds=1.0)
    out = tmp_path / "clip.mp4"

    cut_clip(source, out, start=0.0, duration=0.5, framing=Framing.ORIGINAL)

    assert probe_size(out) == (1280, 720)


@requires_ffmpeg
@pytest.mark.parametrize(
    ("src_w", "src_h", "expected"),
    [
        (1920, 1080, (1080, 1152)),  # 16:9: zoomed to 3/5 of the height, sides trimmed
        (1366, 768, (1080, 1152)),
        (1080, 1080, (1080, 1152)),  # square
        (320, 240, (1080, 1152)),  # 4:3
        (720, 1280, (1080, 1920)),  # 9:16 phone stream: already taller, stays whole
        (1080, 2400, (864, 1920)),  # extra-tall: fitted to the height, nothing cut
    ],
)
def test_blur_foreground_fills_at_least_three_fifths_of_the_height(
    make_video: MakeVideo, tmp_path: Path, src_w: int, src_h: int, expected: tuple[int, int]
) -> None:
    source = make_video(src_w, src_h, seconds=1.0)
    out = tmp_path / "fg.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
           "-t", "0.2", "-vf", foreground_chain(), str(out)]  # fmt: skip

    subprocess.run(cmd, check=True, capture_output=True)

    assert probe_size(out) == expected
