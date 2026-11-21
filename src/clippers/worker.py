"""The background worker: takes job ids off the Redis queue and runs them.

Run it with:  uv run arq clippers.worker.WorkerSettings
Run several (on more machines) to process more videos in parallel.
"""

import logging
from typing import Any

from arq.connections import RedisSettings
from dotenv import find_dotenv, load_dotenv

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
    ctx["store"] = RedisJobStore(ctx["redis"])  # reuse arq's own Redis connection


async def process_job(ctx: dict[str, Any], job_id: str) -> str:
    record = await run_job(job_id, ctx["store"], _settings)
    return record.state


class WorkerSettings:
    """arq reads its configuration from a class like this (≈ a BullMQ Worker's options)."""

    functions = [process_job]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_jobs = 1  # one video at a time: transcription and encoding already use every core
    job_timeout = 3 * 3600  # seconds; a long stream on a slow machine can take a while
    max_tries = 1  # don't silently re-run a failed video; the client can resubmit
