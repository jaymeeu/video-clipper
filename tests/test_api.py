import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clippers.api import create_app
from clippers.jobs import ClipInfo, JobRecord, JobRequest, ServiceSettings, now
from tests.fakes import InMemoryJobStore, RecordingQueue

URL = "https://example.com/stream.mp4"


@pytest.fixture
def settings(tmp_path: Path) -> ServiceSettings:
    return ServiceSettings(redis_url="redis://unused", data_dir=tmp_path / "data", api_key=None)


@pytest.fixture
def store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
def client(
    settings: ServiceSettings, store: InMemoryJobStore, queue: RecordingQueue
) -> Iterator[TestClient]:
    app = create_app(settings, store=store, enqueue=queue)
    with TestClient(app) as client:  # `with` runs the app's startup/shutdown (lifespan)
        yield client


def finished_job(settings: ServiceSettings, store: InMemoryJobStore) -> JobRecord:
    """A done job with one real clip file on disk."""
    t = now()
    record = JobRecord(
        id="abc123",
        state="done",
        request=JobRequest(url=URL),
        clips=[ClipInfo(filename="01-big-win.mp4", start=12.0, duration=30.0, title="Big win")],
        created_at=t,
        updated_at=t,
    )
    asyncio.run(store.save(record))
    job_dir = settings.job_dir(record.id)
    job_dir.mkdir(parents=True)
    (job_dir / "01-big-win.mp4").write_bytes(b"fake mp4 bytes")
    # Files that really exist but must never be served: the job folder always holds
    # moments.json, and other jobs/settings live next to it.
    (job_dir / "moments.json").write_text('{"not": "for clients"}')
    (settings.data_dir / "secret.txt").write_text("not for clients")
    return record


class TestCreateJob:
    def test_queues_job_and_points_to_it(
        self, client: TestClient, store: InMemoryJobStore, queue: RecordingQueue
    ) -> None:
        response = client.post("/jobs", json={"url": URL, "count": 3, "ai": True})

        assert response.status_code == 202
        body = response.json()
        assert body["state"] == "queued" and body["clips"] == []
        assert queue.job_ids == [body["id"]]  # handed to the worker
        assert store.records[body["id"]].request.count == 3  # saved before enqueueing
        assert response.headers["Location"].endswith(f"/jobs/{body['id']}")

    @pytest.mark.parametrize(
        "payload",
        [
            {"url": "/etc/passwd"},  # local paths must never be accepted
            {"url": URL, "count": 0},
            {"url": URL, "framing": "zoom"},
            {"url": URL, "callback": "https://x"},  # unknown field
            {},
        ],
    )
    def test_invalid_requests_are_rejected(
        self, client: TestClient, queue: RecordingQueue, payload: dict[str, object]
    ) -> None:
        response = client.post("/jobs", json=payload)

        assert response.status_code == 422
        assert queue.job_ids == []


class TestGetJob:
    def test_unknown_job_is_404(self, client: TestClient) -> None:
        assert client.get("/jobs/nope").status_code == 404

    def test_finished_job_lists_downloadable_clips(
        self, client: TestClient, settings: ServiceSettings, store: InMemoryJobStore
    ) -> None:
        finished_job(settings, store)

        body = client.get("/jobs/abc123").json()

        assert body["state"] == "done"
        [clip] = body["clips"]
        assert clip["title"] == "Big win"
        assert clip["url"].endswith("/jobs/abc123/clips/01-big-win.mp4")
        download = client.get(clip["url"])
        assert download.status_code == 200
        assert download.headers["content-type"] == "video/mp4"
        assert download.content == b"fake mp4 bytes"


class TestDownloadClip:
    # moments.json exists on disk: only the allow-list stops it. The ../ cases are also
    # stopped earlier by routing (a decoded "/" doesn't match {filename}); kept as a guard.
    @pytest.mark.parametrize(
        "filename", ["moments.json", "02-other.mp4", "..%2Fsecret.txt", "..%2F..%2Fsecret.txt"]
    )
    def test_only_the_jobs_own_clips_are_served(
        self,
        client: TestClient,
        settings: ServiceSettings,
        store: InMemoryJobStore,
        filename: str,
    ) -> None:
        finished_job(settings, store)

        response = client.get(f"/jobs/abc123/clips/{filename}")

        assert response.status_code == 404
        assert b"not for clients" not in response.content  # nothing leaked


class TestApiKey:
    @pytest.fixture
    def settings(self, tmp_path: Path) -> ServiceSettings:  # overrides the module fixture
        return ServiceSettings(
            redis_url="redis://unused", data_dir=tmp_path / "data", api_key="s3cret"
        )

    def test_requests_without_the_right_key_are_refused(self, client: TestClient) -> None:
        assert client.post("/jobs", json={"url": URL}).status_code == 401
        wrong = client.post("/jobs", json={"url": URL}, headers={"X-API-Key": "guess"})
        assert wrong.status_code == 401

    def test_right_key_works(self, client: TestClient) -> None:
        ok = client.post("/jobs", json={"url": URL}, headers={"X-API-Key": "s3cret"})

        assert ok.status_code == 202

    def test_health_check_needs_no_key(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}
