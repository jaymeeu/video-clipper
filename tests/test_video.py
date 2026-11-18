from pathlib import Path

import pytest

from clippers.video import FFmpegError, cut_clip
from tests.media import probe_duration, requires_ffmpeg

pytestmark = requires_ffmpeg  # applies the skip marker to every test in this module


def test_cut_clip_produces_clip_of_requested_duration(sample_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "clip.mp4"

    result = cut_clip(sample_video, out, start=2.0, duration=3.0)

    assert result == out
    assert out.is_file()
    assert probe_duration(out) == pytest.approx(3.0, abs=0.1)


def test_cut_clip_creates_missing_output_dirs(sample_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "clip.mp4"

    cut_clip(sample_video, out, start=0.0, duration=1.0)

    assert out.is_file()


def test_cut_clip_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="source video not found"):
        cut_clip(tmp_path / "nope.mp4", tmp_path / "clip.mp4", start=0.0, duration=1.0)


@pytest.mark.parametrize(
    ("start", "duration"),
    [(-1.0, 3.0), (0.0, 0.0), (0.0, -2.0)],
    ids=["negative-start", "zero-duration", "negative-duration"],
)
def test_cut_clip_invalid_range_raises(
    sample_video: Path, tmp_path: Path, start: float, duration: float
) -> None:
    with pytest.raises(ValueError, match="invalid range"):
        cut_clip(sample_video, tmp_path / "clip.mp4", start=start, duration=duration)


def test_cut_clip_corrupt_source_raises_ffmpeg_error(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_video.mp4"
    fake.write_text("definitely not h264")

    with pytest.raises(FFmpegError) as exc_info:
        cut_clip(fake, tmp_path / "clip.mp4", start=0.0, duration=1.0)

    assert exc_info.value.stderr  # full stderr is preserved for logging
    assert exc_info.value.cmd[0] == "ffmpeg"
