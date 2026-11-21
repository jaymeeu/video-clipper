import subprocess
from pathlib import Path

import pytest

from clippers import pipeline
from clippers.framing import Framing
from clippers.pipeline import CaptionOptions, make_clip
from clippers.transcribe import Transcript, Word, transcribe
from clippers.video import cut_clip, extract_audio
from tests.media import (
    probe_duration,
    probe_size,
    requires_ffmpeg,
    requires_libass,
    requires_say,
)

FAKE_TRANSCRIPT = Transcript(
    language="en",
    language_probability=0.99,
    words=[
        Word(text="Clap", start=0.1, end=0.4, probability=0.9),
        Word(text="for", start=0.4, end=0.6, probability=0.9),
        Word(text="the", start=0.6, end=0.7, probability=0.9),
        Word(text="champion!", start=0.7, end=1.2, probability=0.9),
    ],
)


@pytest.fixture
def fake_transcribe(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Replace Whisper with a canned transcript. Returns the list of audio paths it was given."""
    calls: list[Path] = []

    def _fake(audio: Path, **_: object) -> Transcript:
        calls.append(audio)
        return FAKE_TRANSCRIPT

    # Patch the name where it's *used* (pipeline), not where it's defined (transcribe).
    monkeypatch.setattr(pipeline, "transcribe", _fake)
    return calls


@requires_ffmpeg
def test_extract_audio_is_16khz_mono_wav(sample_video: Path, tmp_path: Path) -> None:
    wav = extract_audio(sample_video, tmp_path / "a.wav", start=1.0, duration=2.0)

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
         "-of", "csv=p=0", str(wav)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert out.stdout.strip() == "16000,1"
    assert probe_duration(wav) == pytest.approx(2.0, abs=0.05)


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    """An existing file that isn't a real video: enough for validation that runs before ffmpeg."""
    path = tmp_path / "dummy.mp4"
    path.write_bytes(b"")
    return path


def test_captions_require_vertical_framing(dummy_video: Path, tmp_path: Path) -> None:
    ass = tmp_path / "c.ass"
    ass.write_text("")

    with pytest.raises(ValueError, match="vertical framing"):
        cut_clip(dummy_video, tmp_path / "o.mp4", start=0, duration=1, subtitles=ass)


def test_subtitles_filename_must_be_plain(dummy_video: Path, tmp_path: Path) -> None:
    ass = tmp_path / "it's, weird.ass"
    ass.write_text("")

    with pytest.raises(ValueError, match="filename"):
        cut_clip(
            dummy_video, tmp_path / "o.mp4", start=0, duration=1,
            framing=Framing.BLUR, subtitles=ass,
        )  # fmt: skip


@requires_ffmpeg
@requires_libass
def test_make_clip_with_captions(
    sample_video: Path, tmp_path: Path, fake_transcribe: list[Path]
) -> None:
    out = tmp_path / "clip.mp4"

    result = make_clip(
        sample_video, out, start=2.0, duration=2.0, framing=Framing.BLUR,
        captions=CaptionOptions(),
    )  # fmt: skip

    assert result.path == out
    assert result.transcript == FAKE_TRANSCRIPT
    assert probe_size(out) == (1080, 1920)
    assert len(fake_transcribe) == 1
    assert not fake_transcribe[0].exists()  # temp audio was cleaned up


@requires_ffmpeg
def test_make_clip_without_speech_skips_subtitles(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    silent = Transcript(language="en", language_probability=0.5, words=[])

    def _silent(audio: Path, **_: object) -> Transcript:
        return silent

    monkeypatch.setattr(pipeline, "transcribe", _silent)

    result = make_clip(
        sample_video, tmp_path / "clip.mp4", start=0, duration=1, captions=CaptionOptions()
    )

    assert result.path.is_file()  # works even on an ffmpeg without libass


@requires_ffmpeg
def test_make_clip_without_captions_never_transcribes(
    sample_video: Path, tmp_path: Path, fake_transcribe: list[Path]
) -> None:
    result = make_clip(sample_video, tmp_path / "clip.mp4", start=0, duration=1, captions=None)

    assert result.transcript is None
    assert fake_transcribe == []


@pytest.mark.slow
@requires_say  # faster-whisper decodes via PyAV's bundled libs: no ffmpeg binary needed
def test_transcribe_real_speech(tmp_path: Path) -> None:
    speech = tmp_path / "speech.aiff"
    subprocess.run(["say", "-o", str(speech), "Hello everyone, welcome to the stream."], check=True)

    transcript = transcribe(speech, model="tiny", language="en")

    spoken = transcript.text.lower()
    assert "hello" in spoken
    assert "stream" in spoken
    starts = [w.start for w in transcript.words]
    assert starts == sorted(starts)
    assert all(w.end >= w.start for w in transcript.words)


@requires_ffmpeg
@requires_libass
def test_make_clip_with_captions_returns_path_as_given(
    sample_video: Path,
    tmp_path: Path,
    fake_transcribe: list[Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)  # so the relative path below lands in tmp_path

    result = make_clip(
        sample_video, Path("out/clip.mp4"), start=0, duration=1, captions=CaptionOptions()
    )

    assert result.path == Path("out/clip.mp4")  # not silently made absolute
    assert (tmp_path / "out" / "clip.mp4").is_file()


@requires_ffmpeg
@requires_libass
def test_make_clip_cuts_captions_from_whole_video_transcript(
    sample_video: Path, tmp_path: Path, fake_transcribe: list[Path]
) -> None:
    whole = Transcript(
        language="en",
        language_probability=0.9,
        words=[
            Word(text="before", start=0.5, end=0.9, probability=0.9),
            Word(text="inside", start=3.2, end=3.6, probability=0.9),
            Word(text="too", start=4.1, end=4.4, probability=0.9),
        ],
    )

    result = make_clip(
        sample_video, tmp_path / "c.mp4", start=3.0, duration=2.0,
        captions=CaptionOptions(), transcript=whole,
    )  # fmt: skip

    assert fake_transcribe == []  # Whisper never ran
    assert result.transcript is not None
    assert [(w.text, round(w.start, 1)) for w in result.transcript.words] == [
        ("inside", 0.2), ("too", 1.1),
    ]  # fmt: skip
    assert probe_size(result.path) == (1080, 1920)
