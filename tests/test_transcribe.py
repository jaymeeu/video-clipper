from collections.abc import Iterator
from pathlib import Path

import faster_whisper
import pytest
from huggingface_hub.errors import LocalEntryNotFoundError

from clippers import transcribe as transcribe_module
from clippers.transcribe import (
    Transcript,
    Word,
    _load_model,  # pyright: ignore[reportPrivateUsage]
    transcribe_cached,
)


class FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel and records how it was constructed."""

    calls: list[dict[str, object]] = []
    cached: set[str] = set()

    def __init__(self, name: str, **kwargs: object) -> None:
        FakeWhisperModel.calls.append({"name": name, **kwargs})
        if kwargs.get("local_files_only") and name not in FakeWhisperModel.cached:
            raise LocalEntryNotFoundError(f"{name} not cached")
        self.name = name


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[FakeWhisperModel]]:
    FakeWhisperModel.calls = []
    FakeWhisperModel.cached = set()
    # _load_model imports WhisperModel at call time, so patching the module attribute works.
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)
    _load_model.cache_clear()  # don't let a model cached by another test skip our code
    yield FakeWhisperModel
    _load_model.cache_clear()


def test_cached_model_loads_without_network(fake_whisper: type[FakeWhisperModel]) -> None:
    fake_whisper.cached = {"small"}

    _load_model("small")

    assert len(fake_whisper.calls) == 1
    assert fake_whisper.calls[0]["local_files_only"] is True


def test_missing_model_is_downloaded_once(
    fake_whisper: type[FakeWhisperModel], caplog: pytest.LogCaptureFixture
) -> None:
    _load_model("medium")

    assert [c.get("local_files_only") for c in fake_whisper.calls] == [True, None]
    assert "downloading whisper model 'medium'" in caplog.text


def test_model_is_loaded_once_per_process(fake_whisper: type[FakeWhisperModel]) -> None:
    fake_whisper.cached = {"small"}

    first = _load_model("small")
    second = _load_model("small")

    assert first is second
    assert len(fake_whisper.calls) == 1


class TestTranscribeCached:
    @pytest.fixture
    def counting_transcribe(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> list[tuple[Path, str]]:
        """Fake transcriber recording its calls; cache in a temp dir, not ~/.cache."""
        monkeypatch.setenv("CLIPPERS_CACHE_DIR", str(tmp_path / "cache"))
        calls: list[tuple[Path, str]] = []

        def fake(audio: Path, *, model: str = "small", language: str | None = None) -> Transcript:
            calls.append((audio, model))
            return Transcript(
                language="en",
                language_probability=0.9,
                words=[Word(text="hello", start=0, end=0.5, probability=0.9)],
            )

        # transcribe_cached looks up `transcribe` in its own module at call time.
        monkeypatch.setattr(transcribe_module, "transcribe", fake)
        return calls

    def test_second_call_uses_cache(
        self, counting_transcribe: list[tuple[Path, str]], tmp_path: Path
    ) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video")

        first = transcribe_cached(video)
        second = transcribe_cached(video)

        assert first == second
        assert len(counting_transcribe) == 1

    def test_changed_file_or_model_misses_cache(
        self, counting_transcribe: list[tuple[Path, str]], tmp_path: Path
    ) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video")
        transcribe_cached(video)

        transcribe_cached(video, model="tiny")  # different model
        video.write_bytes(b"a longer, different video")  # different size and mtime
        transcribe_cached(video)

        assert len(counting_transcribe) == 3

    def test_corrupt_cache_file_is_ignored(
        self, counting_transcribe: list[tuple[Path, str]], tmp_path: Path
    ) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video")
        transcribe_cached(video)
        for cached in (tmp_path / "cache" / "transcripts").glob("*.json"):
            cached.write_text("{ not json")

        transcript = transcribe_cached(video)

        assert transcript.words[0].text == "hello"
        assert len(counting_transcribe) == 2

    def test_missing_video_raises(self, counting_transcribe: list[tuple[Path, str]]) -> None:
        with pytest.raises(FileNotFoundError):
            transcribe_cached(Path("/nonexistent/video.mp4"))
