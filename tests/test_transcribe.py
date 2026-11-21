from collections.abc import Iterator

import faster_whisper
import pytest
from huggingface_hub.errors import LocalEntryNotFoundError

from clippers.transcribe import _load_model  # pyright: ignore[reportPrivateUsage]


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
