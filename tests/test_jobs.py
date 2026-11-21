import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from clippers import autoclip
from clippers.autoclip import AutoOptions, AutoResult
from clippers.batch import ClipOutcome
from clippers.framing import Framing
from clippers.ingest import DownloadError
from clippers.jobs import JobRecord, JobRequest, ServiceSettings, now, run_job
from clippers.moments import Moment, MomentsFile
from tests.fakes import InMemoryJobStore

URL = "https://example.com/stream.mp4"


def settings(tmp_path: Path) -> ServiceSettings:
    return ServiceSettings(redis_url="redis://unused", data_dir=tmp_path / "data", api_key=None)


def queued(job_id: str = "job1", **request: Any) -> JobRecord:
    t = now()
    return JobRecord(
        id=job_id,
        state="queued",
        request=JobRequest(url=URL, **request),
        created_at=t,
        updated_at=t,
    )


def fake_pipeline(
    monkeypatch: pytest.MonkeyPatch, *, ok: int = 2, failed: int = 0, error: Exception | None = None
) -> list[dict[str, Any]]:
    """Replace autoclip.auto_clip; returns the list of calls it received."""
    calls: list[dict[str, Any]] = []

    def fake_auto_clip(video: str, out_dir: Path, options: AutoOptions, **kw: Any) -> AutoResult:
        calls.append({"video": video, "out_dir": out_dir, "options": options, **kw})
        for stage in ("downloading", "transcribing", "rendering"):
            kw["progress"](stage)
        if error is not None:
            raise error
        moments = [Moment(start=10 * i, duration=20, title=f"Clip {i}") for i in range(ok + failed)]
        outcomes = [
            ClipOutcome(number=i + 1, moment=m, path=out_dir / f"0{i + 1}.mp4")
            if i < ok
            else ClipOutcome(number=i + 1, moment=m, error="ffmpeg failed")
            for i, m in enumerate(moments)
        ]
        plan = MomentsFile(source=video, moments=moments)
        return AutoResult(plan=plan, moments_path=out_dir / "moments.json", outcomes=outcomes)

    monkeypatch.setattr(autoclip, "auto_clip", fake_auto_clip)
    return calls


def run(job_id: str, store: InMemoryJobStore, tmp_path: Path) -> JobRecord:
    return asyncio.run(run_job(job_id, store, settings(tmp_path)))


class TestRunJob:
    def test_success_records_stages_then_clips(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls = fake_pipeline(monkeypatch, ok=2)
        store = InMemoryJobStore()
        asyncio.run(store.save(queued(count=2, ai=True, framing=Framing.CROP)))

        final = run("job1", store, tmp_path)

        assert final.state == "done"
        assert [c.filename for c in final.clips] == ["01.mp4", "02.mp4"]
        assert [c.title for c in final.clips] == ["Clip 0", "Clip 1"]
        # Progress was saved stage by stage, in order, while the pipeline ran.
        stages = [(r.state, r.stage) for r in store.history]
        assert stages == [
            ("queued", None),
            ("running", "starting"),
            ("running", "downloading"),
            ("running", "transcribing"),
            ("running", "rendering"),
            ("done", None),
        ]
        # The request's options reached the pipeline; output goes to the job's own folder.
        options = calls[0]["options"]
        assert (options.count, options.use_ai, options.framing) == (2, True, Framing.CROP)
        assert calls[0]["out_dir"] == tmp_path / "data" / "jobs" / "job1"

    def test_partial_failure_is_done_with_count(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_pipeline(monkeypatch, ok=1, failed=2)
        store = InMemoryJobStore()
        asyncio.run(store.save(queued()))

        final = run("job1", store, tmp_path)

        assert (final.state, len(final.clips), final.failed_clips) == ("done", 1, 2)

    def test_every_clip_failing_fails_the_job(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_pipeline(monkeypatch, ok=0, failed=3)
        store = InMemoryJobStore()
        asyncio.run(store.save(queued()))

        final = run("job1", store, tmp_path)

        assert (final.state, final.error) == ("failed", "every clip failed to render")

    def test_expected_error_message_reaches_the_client(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_pipeline(monkeypatch, error=DownloadError("could not download: HTTP 404"))
        store = InMemoryJobStore()
        asyncio.run(store.save(queued()))

        final = run("job1", store, tmp_path)

        assert (final.state, final.stage) == ("failed", None)
        assert final.error == "could not download: HTTP 404"

    def test_bug_is_hidden_from_client_but_logged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fake_pipeline(monkeypatch, error=KeyError("internal detail"))
        store = InMemoryJobStore()
        asyncio.run(store.save(queued()))

        final = run("job1", store, tmp_path)

        assert (final.state, final.error) == ("failed", "internal error")
        assert "job job1 crashed" in caplog.text  # with traceback, for us

    def test_unknown_job_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(LookupError):
            run("nope", InMemoryJobStore(), tmp_path)


class TestJobRequest:
    @pytest.mark.parametrize(
        "url", ["/etc/passwd", "file:///etc/passwd", "downloads/video.mp4", "ftp://x/y.mp4"]
    )
    def test_only_web_urls_are_accepted(self, url: str) -> None:
        with pytest.raises(ValidationError, match="http"):
            JobRequest(url=url)

    def test_limits_and_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            JobRequest(url=URL, count=500)
        with pytest.raises(ValidationError):
            JobRequest.model_validate({"url": URL, "cout": 3})  # typo'd field

    def test_maps_to_pipeline_options(self) -> None:
        options = JobRequest(url=URL, count=3, captions=False, language="en").options()

        assert (options.count, options.captions, options.language) == (3, False, "en")
        assert options.use_transcript is True
