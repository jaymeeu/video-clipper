import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from clippers import cli
from clippers.audio import loudness_per_second
from clippers.cli import app
from clippers.detect import NoHighlightsError, detect_moments
from clippers.moments import load_moments
from clippers.transcribe import Transcript, Word
from tests.media import requires_ffmpeg

pytestmark = requires_ffmpeg

# Quiet tone with two loud bursts: 60-70s (x33 volume, ~+30 dB) and 130-135s (x10, ~+20 dB).
_VOLUME = "if(between(t,60,70),1,if(between(t,130,135),0.3,0.03))"


@pytest.fixture(scope="module")
def bursty_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("detect") / "bursty.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=5",
        "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=8000",
        "-af", f"volume='{_VOLUME}':eval=frame",
        "-t", "180", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def test_loudness_has_one_value_per_second_and_sees_bursts(bursty_video: Path) -> None:
    loudness = loudness_per_second(bursty_video)

    assert loudness.size == pytest.approx(180, abs=1)
    assert loudness[65] - loudness[20] == pytest.approx(30, abs=2)
    assert loudness[132] - loudness[20] == pytest.approx(20, abs=2)


def test_detect_finds_bursts_in_score_order(bursty_video: Path) -> None:
    plan = detect_moments(str(bursty_video), bursty_video, count=5, duration=20)

    starts = [m.start for m in plan.moments]
    assert len(starts) == 2
    assert starts[0] <= 60 and starts[0] + 20 >= 70  # loudest burst first, fully inside
    assert starts[1] <= 130 and starts[1] + 20 >= 135
    assert all(m.reason and "dB louder" in m.reason for m in plan.moments)
    assert plan.source == str(bursty_video.resolve())


def test_detect_on_even_audio_raises(sample_video: Path) -> None:
    with pytest.raises(NoHighlightsError):
        detect_moments(str(sample_video), sample_video, count=3, duration=5)


def test_cli_detect_writes_loadable_moments_file(bursty_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "m.json"

    result = CliRunner().invoke(
        app, ["detect", "--no-transcript", str(bursty_video), "-n", "3", "-d", "20", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == str(out)
    assert "next: clippers batch" in result.stderr
    plan = load_moments(out)  # round-trips through our own validation
    assert len(plan.moments) == 2
    assert plan.moments[0].score is not None


def test_cli_detect_silent_video_fails_cleanly(sample_video: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["detect", "--no-transcript", str(sample_video), "-d", "5"])

    assert result.exit_code == 1
    assert "no moment stood out" in result.stderr


def _reactions_at(start: float) -> Transcript:
    """A transcript that is ordinary chat except for a burst of reactions at `start`."""
    chat = [Word(text="okay", start=t, end=t + 0.3, probability=0.9) for t in range(0, 180, 2)]
    hype = [
        Word(text=text, start=start + i, end=start + i + 0.3, probability=0.9)
        for i, text in enumerate(["Omo!", "chai", "no", "way", "hahaha", "wahala", "Jesu!"])
    ]
    return Transcript(
        language="en", language_probability=0.9, words=sorted(chat + hype, key=lambda w: w.start)
    )


def test_transcript_reactions_can_outrank_quiet_audio(bursty_video: Path) -> None:
    # 100-107s is quiet in the audio, but full of reactions in the transcript.
    plan = detect_moments(
        str(bursty_video), bursty_video, count=5, duration=20, transcript=_reactions_at(100)
    )

    reaction_picks = [m for m in plan.moments if m.start <= 100 and m.start + 20 >= 107]
    assert reaction_picks, [m.start for m in plan.moments]
    assert reaction_picks[0].reason is not None
    assert "reactions ('omo'" in reaction_picks[0].reason


def test_cli_detect_uses_cached_transcript(
    bursty_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def fake_transcribe_cached(video: Path, **_: object) -> Transcript:
        calls.append(video)
        return _reactions_at(100)

    monkeypatch.setattr(cli, "transcribe_cached", fake_transcribe_cached)
    out = tmp_path / "m.json"

    result = CliRunner().invoke(app, ["detect", str(bursty_video), "-d", "20", "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert calls == [bursty_video]
    assert any("reactions" in (m.reason or "") for m in load_moments(out).moments)
