"""Clip jobs: what a client asks for, how a job's progress is stored, and how it runs.

Independent of HTTP (api.py) and of the queue (worker.py), so it can be tested alone.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis

from clippers import autoclip
from clippers.ai import AIScoringError
from clippers.autoclip import AutoOptions
from clippers.framing import Framing
from clippers.ingest import DownloadError, is_url
from clippers.netguard import check_public_url
from clippers.video import FFmpegError

logger = logging.getLogger(__name__)

JobState = Literal["queued", "running", "done", "failed"]

# Errors that mean "this video/request can't be processed", shown to the client as-is.
# (netguard.UnsafeURLError is a ValueError, so a blocked URL lands here too.)
# Anything else is a bug: logged with a traceback, reported as a generic internal error.
_EXPECTED_ERRORS = (AIScoringError, DownloadError, FFmpegError, FileNotFoundError, ValueError)


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    redis_url: str
    data_dir: Path  # job outputs and downloads live here
    api_key: str | None  # when set, clients must send it as X-API-Key
    # How long finished jobs (records and clips), downloads and caches are kept.
    retention_days: float = 7.0

    @classmethod
    def from_env(cls) -> "ServiceSettings":
        return cls(
            redis_url=os.environ.get("CLIPPERS_REDIS_URL", "redis://localhost:6379"),
            data_dir=Path(os.environ.get("CLIPPERS_DATA_DIR", "data")),
            api_key=os.environ.get("CLIPPERS_API_KEY") or None,
            retention_days=float(os.environ.get("CLIPPERS_RETENTION_DAYS", "7")),
        )

    def job_dir(self, job_id: str) -> Path:
        return self.data_dir / "jobs" / job_id

    @property
    def retention_seconds(self) -> int:
        return int(self.retention_days * 24 * 3600)


class JobRequest(BaseModel):
    """What a client POSTs to /jobs."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="http(s) URL of the video: a direct file or a platform page")
    count: int = Field(default=5, ge=1, le=20)
    duration: int = Field(default=30, ge=5, le=180, description="typical clip length (s)")
    framing: Framing = Framing.BLUR
    captions: bool = True
    language: str | None = Field(default=None, max_length=10, description="e.g. 'en'")
    ai: bool = Field(default=False, description="also score with OpenAI (costs a little)")

    @field_validator("url")
    @classmethod
    def _must_be_web_url(cls, value: str) -> str:
        # Never accept local paths here: a client could otherwise make the server read
        # (and clip) arbitrary files from its own disk.
        if not is_url(value):
            raise ValueError("must be an http(s) URL")
        return value

    def options(self) -> AutoOptions:
        return AutoOptions(
            count=self.count,
            duration=self.duration,
            framing=self.framing,
            captions=self.captions,
            language=self.language,
            use_ai=self.ai,
        )


class ClipInfo(BaseModel):
    filename: str
    start: float
    duration: float
    title: str | None = None
    reason: str | None = None
    score: float | None = None


class JobRecord(BaseModel):
    """Everything known about a job. Stored as JSON; the worker updates it as it goes."""

    id: str
    state: JobState
    stage: str | None = None  # e.g. "transcribing", while running
    error: str | None = None
    request: JobRequest
    clips: list[ClipInfo] = []
    failed_clips: int = 0
    created_at: datetime
    updated_at: datetime

    def updated(self, **changes: object) -> "JobRecord":
        return self.model_copy(update={**changes, "updated_at": now()})


def now() -> datetime:
    return datetime.now(UTC)


class JobStore(Protocol):
    async def get(self, job_id: str) -> JobRecord | None: ...
    async def save(self, record: JobRecord) -> None: ...
    async def recent(self, limit: int) -> list[JobRecord]:
        """The newest jobs first (expired ones are left out)."""
        ...


class RedisJobStore:
    """Job records as JSON strings in Redis. Each save resets the record's expiry, so a
    record lives `ttl_seconds` after the job's last update; cleanup.py then removes the
    job's files once the record is gone."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    # A sorted set of job ids scored by creation time: Redis's way to keep an ordered
    # index (≈ an index on created_at). Records expire on their own; the index is trimmed
    # by age on every save and cleaned of expired ids whenever it's read.
    _INDEX = "clippers:jobs"

    @staticmethod
    def _key(job_id: str) -> str:
        return f"clippers:job:{job_id}"

    async def get(self, job_id: str) -> JobRecord | None:
        raw = await self._redis.get(self._key(job_id))
        return JobRecord.model_validate_json(raw) if raw is not None else None

    async def save(self, record: JobRecord) -> None:
        created = record.created_at.timestamp()
        await self._redis.set(self._key(record.id), record.model_dump_json(), ex=self._ttl_seconds)
        await self._redis.zadd(self._INDEX, {record.id: created}, nx=True)  # nx: keep first
        await self._redis.zremrangebyscore(
            self._INDEX, "-inf", now().timestamp() - self._ttl_seconds
        )

    async def recent(self, limit: int) -> list[JobRecord]:
        # redis-py's annotation for zrevrange has an untyped callable parameter.
        ids: list[bytes] = await self._redis.zrevrange(self._INDEX, 0, limit - 1)  # pyright: ignore[reportUnknownMemberType]
        if not ids:
            return []
        raws: list[bytes | None] = await self._redis.mget([self._key(i.decode()) for i in ids])
        expired = [i for i, raw in zip(ids, raws, strict=True) if raw is None]
        if expired:
            await self._redis.zrem(self._INDEX, *expired)
        return [JobRecord.model_validate_json(raw) for raw in raws if raw is not None]


async def run_job(job_id: str, store: JobStore, settings: ServiceSettings) -> JobRecord:
    """Run one job start to finish, recording progress in `store`. Never raises for a
    bad video: failures end up in the record, where the client can read them."""
    found = await store.get(job_id)
    if found is None:
        raise LookupError(f"job {job_id} not found")  # a queue/store mismatch: a real bug
    # A separately typed variable: `found`'s None-check doesn't carry into the closure below
    # (a closure may run later), so the checker would still see `JobRecord | None` there.
    record: JobRecord = found.updated(state="running", stage="starting")
    await store.save(record)

    loop = asyncio.get_running_loop()

    def progress(stage: str) -> None:
        # Called from the worker thread that runs the pipeline, not from the event loop.
        # Hand the save to the loop and wait for it, so stages are stored in order.
        nonlocal record
        record = record.updated(stage=stage)
        asyncio.run_coroutine_threadsafe(store.save(record), loop).result()

    try:
        # Check the URL again right before downloading: the job may have waited in the
        # queue, and DNS answers can change in the meantime.
        await asyncio.to_thread(check_public_url, record.request.url)
        # The pipeline is blocking (ffmpeg, Whisper): run it in a thread so the event
        # loop (and arq's heartbeats) stay responsive. ≈ a worker_thread in Node.
        result = await asyncio.to_thread(
            autoclip.auto_clip,
            record.request.url,
            settings.job_dir(job_id),
            record.request.options(),
            download_dir=settings.data_dir / "downloads",
            progress=progress,
        )
    except _EXPECTED_ERRORS as e:
        record = record.updated(state="failed", stage=None, error=str(e))
    except Exception:
        logger.exception("job %s crashed", job_id)
        record = record.updated(state="failed", stage=None, error="internal error")
    else:
        clips = [
            ClipInfo(
                filename=o.path.name,
                start=o.moment.start,
                duration=o.moment.duration,
                title=o.moment.title,
                reason=o.moment.reason,
                score=o.moment.score,
            )
            for o in result.outcomes
            if o.path is not None
        ]
        failed = sum(not o.ok for o in result.outcomes)
        record = record.updated(
            state="done" if clips else "failed",
            stage=None,
            clips=clips,
            failed_clips=failed,
            error=None if clips else "every clip failed to render",
        )
    await store.save(record)
    logger.info("job %s finished: %s (%d clips)", job_id, record.state, len(record.clips))
    return record
