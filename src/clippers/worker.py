"""The background worker: takes job ids off the Redis queue and runs them.

Run it with:  uv run arq clippers.worker.WorkerSettings
Run several (on more machines) to process more videos in parallel.
"""

import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from dotenv import find_dotenv, load_dotenv

from clippers.cleanup import cleanup
from clippers.jobs import RedisJobStore, ServiceSettings, run_job
from clippers.logs import configure_logging

# The arq CLI imports this module directly (no `clippers` CLI callback runs), so load .env
# here, before WorkerSettings reads its settings below.
load_dotenv(find_dotenv(usecwd=True), override=False)
_settings = ServiceSettings.from_env()


async def startup(ctx: dict[str, Any]) -> None:
    # arq configures logging for its own "arq" logger only; without this, our progress
    # messages (transcribing, rendering, ...) had no handler and were silently dropped.
    configure_logging(verbose=False, timestamps=True)
    # arq prints its own records through its own handler; stop them also bubbling up to
    # the root handler added above, or every arq line appears twice.
    logging.getLogger("arq").propagate = False
    ctx["store"] = RedisJobStore(
        ctx["redis"], _settings.retention_seconds
    )  # reuse arq's own Redis connection


async def cleanup_old_files(ctx: dict[str, Any]) -> str:
    report = await cleanup(ctx["store"], _settings)
    return f"{report.jobs_removed} jobs, {report.files_removed} files, {report.bytes_freed} bytes"


async def process_job(ctx: dict[str, Any], job_id: str) -> str:
    record = await run_job(job_id, ctx["store"], _settings)
    return record.state


class WorkerSettings:
    """arq reads its configuration from a class like this (≈ a BullMQ Worker's options)."""

    functions = [process_job]
    # Every hour at :17 (an odd minute, so many services don't all wake at :00), and once
    # when the worker starts. unique=True (the default): with several workers, only one runs it.
    cron_jobs = [cron(cleanup_old_files, minute=17, run_at_startup=True)]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_jobs = 1  # one video at a time: transcription and encoding already use every core
    job_timeout = 3 * 3600  # seconds; a long stream on a slow machine can take a while
    max_tries = 1  # don't silently re-run a failed video; the client can resubmit
