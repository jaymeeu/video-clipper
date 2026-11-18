from pathlib import Path

import pytest
from typer.testing import CliRunner

from clippers.cli import app
from tests.media import probe_duration, requires_ffmpeg

runner = CliRunner()


@requires_ffmpeg
def test_cut_writes_clip_and_prints_path(sample_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "clip.mp4"

    result = runner.invoke(
        app, ["cut", str(sample_video), "--start", "0:02", "--duration", "2", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == str(out)
    assert probe_duration(out) == pytest.approx(2.0, abs=0.1)


def test_cut_bad_timestamp_is_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["cut", str(tmp_path / "x.mp4"), "--start", "1:60"])

    assert result.exit_code == 2  # click convention: 2 = bad usage
    assert "invalid timestamp" in result.stderr


def test_cut_missing_video_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["cut", str(tmp_path / "nope.mp4"), "--start", "0"])

    assert result.exit_code == 1
    assert "error: source video not found" in result.stderr
    assert "Traceback" not in result.output


@requires_ffmpeg
def test_cut_corrupt_video_fails_cleanly(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_text("not a video")

    result = runner.invoke(app, ["cut", str(fake), "--start", "0", "-o", str(tmp_path / "o.mp4")])

    assert result.exit_code == 1
    assert "error: ffmpeg failed" in result.stderr


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])

    assert "cut" in result.output
