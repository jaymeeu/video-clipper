import asyncio
import os
import time
from pathlib import Path

import pytest

from clippers import cache
from clippers.cleanup import CleanupReport, cleanup
from clippers.jobs import JobRecord, JobRequest, ServiceSettings, now
from tests.fakes import InMemoryJobStore

DAY = 86_400
NOW = time.time()


def aged(path: Path, days: float) -> Path:
    """Backdate a file or folder's modification time by `days`."""
    t = NOW - days * DAY
    os.utime(path, (t, t))
    return path


def job_dir(data: Path, job_id: str, days_old: float) -> Path:
    d = data / "jobs" / job_id
    d.mkdir(parents=True)
    (d / "01-clip.mp4").write_bytes(b"x" * 1000)
    (d / "moments.json").write_text("{}")
    return aged(d, days_old)


def record(job_id: str) -> JobRecord:
    t = now()
    return JobRecord(
        id=job_id,
        state="done",
        request=JobRequest(url="https://example.com/v.mp4"),
        created_at=t,
        updated_at=t,
    )


@pytest.fixture
def settings(tmp_path: Path) -> ServiceSettings:
    return ServiceSettings(
        redis_url="redis://unused", data_dir=tmp_path / "data", api_key=None, retention_days=7
    )


def run(store: InMemoryJobStore, settings: ServiceSettings) -> CleanupReport:
    return asyncio.run(cleanup(store, settings, now=NOW))


class TestJobFolders:
    def test_expired_jobs_go_listed_jobs_stay(self, settings: ServiceSettings) -> None:
        data = settings.data_dir
        expired = job_dir(data, "a" * 32, days_old=8)  # record expired from Redis
        listed = job_dir(data, "b" * 32, days_old=8)  # record still there: API lists it
        store = InMemoryJobStore()
        asyncio.run(store.save(record("b" * 32)))

        report = run(store, settings)

        assert not expired.exists()
        assert listed.exists()  # never delete a clip the API still advertises
        assert report.jobs_removed == 1
        assert report.bytes_freed == 1002  # 1000-byte clip + "{}"

    def test_young_folders_are_kept_even_without_a_record(self, settings: ServiceSettings) -> None:
        # A job folder can briefly exist before its record is visible (or Redis was just
        # flushed): within the grace period, leave it alone.
        fresh = job_dir(settings.data_dir, "c" * 32, days_old=0.01)  # ~15 minutes

        run(InMemoryJobStore(), settings)

        assert fresh.exists()

    def test_only_job_id_folders_are_ever_removed(self, settings: ServiceSettings) -> None:
        jobs = settings.data_dir / "jobs"
        jobs.mkdir(parents=True)
        not_a_job = aged(_mkdir(jobs / "important-backup"), days=30)
        target = _mkdir(settings.data_dir / "elsewhere")
        (target / "precious.txt").write_text("keep me")
        link = jobs / ("d" * 32)
        link.symlink_to(target, target_is_directory=True)
        old = NOW - 30 * DAY
        os.utime(link, (old, old), follow_symlinks=False)

        run(InMemoryJobStore(), settings)

        assert not_a_job.exists()
        assert (target / "precious.txt").read_text() == "keep me"  # symlink not followed

    def test_missing_data_folder_is_fine(self, settings: ServiceSettings) -> None:
        assert run(InMemoryJobStore(), settings).jobs_removed == 0


class TestDownloadsAndCache:
    def test_old_files_go_recent_ones_stay(self, settings: ServiceSettings) -> None:
        data = settings.data_dir
        downloads = _mkdir(data / "downloads")
        old_video = aged(_write(downloads / "youtube-old.mp4", 500), days=10)
        new_video = aged(_write(downloads / "youtube-new.mp4", 500), days=2)
        old_cache = aged(_write(data / "cache" / "ai" / "old.json", 20), days=10)
        new_cache = aged(_write(data / "cache" / "transcripts" / "new.json", 20), days=1)
        model = aged(_write(data / "huggingface" / "model.bin", 50), days=365)

        report = run(InMemoryJobStore(), settings)

        assert not old_video.exists() and not old_cache.exists()
        assert new_video.exists() and new_cache.exists()
        assert model.exists()  # Whisper models are never touched
        assert (report.files_removed, report.bytes_freed) == (2, 520)

    def test_retention_is_configurable(self, tmp_path: Path) -> None:
        short = ServiceSettings(
            redis_url="redis://unused", data_dir=tmp_path / "d", api_key=None, retention_days=1
        )
        video = aged(_write(short.data_dir / "downloads" / "v.mp4", 10), days=2)

        run(InMemoryJobStore(), short)

        assert not video.exists()


def test_cache_hit_marks_entry_as_recently_used(
    settings: ServiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A transcript cached 10 days ago but used today must survive cleanup.
    monkeypatch.setenv("CLIPPERS_CACHE_DIR", str(settings.data_dir / "cache"))
    path = cache.cache_path("transcripts", "some-video")
    cache.save(path, record("e" * 32))
    aged(path, days=10)

    assert cache.load(path, JobRecord) is not None  # used today
    run(InMemoryJobStore(), settings)

    assert path.exists()


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path
