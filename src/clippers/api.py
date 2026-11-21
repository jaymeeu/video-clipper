"""HTTP API for the clipper: submit a video, poll the job, download the clips.

Run it with:  uv run uvicorn --factory clippers.api:make_app --reload
(and a worker:  uv run arq clippers.worker.WorkerSettings)
Interactive docs at http://localhost:8000/docs
"""

import asyncio
import logging
import secrets
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from dotenv import find_dotenv, load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clippers.jobs import (
    ClipInfo,
    JobRecord,
    JobRequest,
    JobState,
    JobStore,
    RedisJobStore,
    ServiceSettings,
    now,
)
from clippers.netguard import UnsafeURLError, check_public_url

logger = logging.getLogger(__name__)

Enqueue = Callable[[str], Awaitable[None]]
"""Puts a job id on the work queue."""


class ClipView(ClipInfo):
    url: str  # where to download it


class JobView(BaseModel):
    """What clients see for a job (the stored record, plus download URLs)."""

    id: str
    state: JobState
    stage: str | None
    error: str | None
    clips: list[ClipView]
    failed_clips: int


# Dependencies: FastAPI calls these per request and passes the results into handlers
# (≈ Express middleware that sets req.store, but typed and declared per route).
def get_store(request: Request) -> JobStore:
    return request.app.state.store


def get_enqueue(request: Request) -> Enqueue:
    return request.app.state.enqueue


StoreDep = Annotated[JobStore, Depends(get_store)]
EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]


def _view(record: JobRecord, request: Request) -> JobView:
    clips = [
        ClipView(
            **clip.model_dump(),
            url=str(request.url_for("download_clip", job_id=record.id, filename=clip.filename)),
        )
        for clip in record.clips
    ]
    return JobView(
        id=record.id,
        state=record.state,
        stage=record.stage,
        error=record.error,
        clips=clips,
        failed_clips=record.failed_clips,
    )


def create_app(
    settings: ServiceSettings | None = None,
    *,
    store: JobStore | None = None,
    enqueue: Enqueue | None = None,
) -> FastAPI:
    """Build the app. Tests pass `store`/`enqueue` fakes; otherwise Redis is used."""
    settings = settings or ServiceSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Runs once at startup (before `yield`) and shutdown (after): like the code around
        # app.listen() in Node, for opening and closing connections.
        if store is not None and enqueue is not None:
            app.state.store, app.state.enqueue = store, enqueue
            yield
            return
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

        async def enqueue_job(job_id: str) -> None:
            await pool.enqueue_job("process_job", job_id, _job_id=job_id)

        app.state.store, app.state.enqueue = RedisJobStore(pool), enqueue_job
        if settings.api_key is None:
            logger.warning("CLIPPERS_API_KEY is not set: the API accepts unauthenticated requests")
        try:
            yield
        finally:
            await pool.aclose()

    def check_api_key(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
        # /health stays open: load balancers and uptime checks can't send secrets.
        if settings.api_key is None or request.url.path == "/health":
            return
        # compare_digest takes the same time whether the first or last character differs,
        # so an attacker can't guess the key one character at a time by timing responses.
        if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or wrong X-API-Key")

    app = FastAPI(
        title="clippers",
        description="Turn videos into captioned vertical highlight clips.",
        lifespan=lifespan,
        dependencies=[Depends(check_api_key)],  # applies to every route
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        body: JobRequest,
        request: Request,
        response: Response,
        store: StoreDep,
        enqueue: EnqueueDep,
    ) -> JobView:
        """Queue a video for clipping. Returns immediately; poll the job for progress."""
        try:
            # DNS lookups block, so run the check in a thread (the worker checks again).
            await asyncio.to_thread(check_public_url, body.url)
        except UnsafeURLError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"url: {e}") from e
        created = now()
        record = JobRecord(
            id=uuid.uuid4().hex,
            state="queued",
            request=body,
            created_at=created,
            updated_at=created,
        )
        await store.save(record)  # save first: the worker may start before we return
        await enqueue(record.id)
        response.headers["Location"] = str(request.url_for("get_job", job_id=record.id))
        return _view(record, request)

    async def _load(store: JobStore, job_id: str) -> JobRecord:
        record = await store.get(job_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
        return record

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str, request: Request, store: StoreDep) -> JobView:
        """Job state ("queued", "running", "done", "failed"), current stage and clips."""
        return _view(await _load(store, job_id), request)

    @app.get("/jobs/{job_id}/clips/{filename}", response_class=FileResponse)
    async def download_clip(job_id: str, filename: str, store: StoreDep) -> FileResponse:
        """Download one finished clip (MP4)."""
        record = await _load(store, job_id)
        # Only serve names the job itself produced: a filename like "../../.env" can't
        # match, so the URL can't be used to read other files (path traversal).
        if filename not in {clip.filename for clip in record.clips}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such clip")
        return FileResponse(
            settings.job_dir(job_id) / filename, media_type="video/mp4", filename=filename
        )

    return app


def make_app() -> FastAPI:
    """Entry point for `uvicorn --factory clippers.api:make_app`: load .env, build the app.

    A factory rather than a module-level `app = ...`, so importing this module (in tests,
    say) has no side effects: no .env loaded, no settings read.
    """
    load_dotenv(find_dotenv(usecwd=True), override=False)
    return create_app()
