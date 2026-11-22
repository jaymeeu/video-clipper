"""Delete old job files, downloads and cache entries so the data folder doesn't grow forever.

What goes, under the service's data directory:
- jobs/<id>/    once the job's record has expired from the store (so a clip is never
                deleted while the API still lists it) and the folder is over an hour old
- downloads/*   source videos older than the retention period (re-downloaded if needed)
- cache/**      cached transcripts and AI answers older than the retention period
Everything else (e.g. huggingface/, the Whisper models) is left alone. Only folders named
like a job id are ever removed, and symlinks are never followed.
"""

import asyncio
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from clippers.jobs import JobStore, ServiceSettings

logger = logging.getLogger(__name__)

_JOB_ID = re.compile(r"[0-9a-f]{32}")  # uuid4().hex, as created by the API
GRACE_SECONDS = 3600  # never touch a job folder younger than this, record or not


@dataclass(frozen=True, slots=True)
class CleanupReport:
    jobs_removed: int = 0
    files_removed: int = 0
    bytes_freed: int = 0

    def __add__(self, other: "CleanupReport") -> "CleanupReport":
        return CleanupReport(
            self.jobs_removed + other.jobs_removed,
            self.files_removed + other.files_removed,
            self.bytes_freed + other.bytes_freed,
        )


def _size(path: Path) -> int:
    """Total bytes of a file, or of all regular files under a folder."""
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def _job_dirs_older_than(jobs_dir: Path, cutoff: float) -> list[Path]:
    if not jobs_dir.is_dir():
        return []
    return [
        d
        for d in jobs_dir.iterdir()
        if d.is_dir()
        and not d.is_symlink()
        and _JOB_ID.fullmatch(d.name)
        and d.stat().st_mtime < cutoff
    ]


def _remove_dirs(dirs: list[Path]) -> CleanupReport:
    report = CleanupReport()
    for d in dirs:
        size = _size(d)
        shutil.rmtree(d)
        report += CleanupReport(jobs_removed=1, bytes_freed=size)
    return report


def _remove_old_files(folder: Path, cutoff: float) -> CleanupReport:
    """Delete regular files (any depth) last modified before `cutoff`."""
    report = CleanupReport()
    if not folder.is_dir():
        return report
    for f in folder.rglob("*"):
        if f.is_file() and not f.is_symlink() and f.stat().st_mtime < cutoff:
            size = f.stat().st_size
            f.unlink()
            report += CleanupReport(files_removed=1, bytes_freed=size)
    return report


async def cleanup(
    store: JobStore, settings: ServiceSettings, *, now: float | None = None
) -> CleanupReport:
    """Remove expired jobs' folders and stale downloads/cache files. Safe to run anytime."""
    now = time.time() if now is None else now
    expired_before = now - settings.retention_seconds
    data = settings.data_dir

    # Filesystem work blocks, so it runs in a thread; the store lookups are async.
    candidates = await asyncio.to_thread(_job_dirs_older_than, data / "jobs", now - GRACE_SECONDS)
    orphans = [d for d in candidates if await store.get(d.name) is None]

    report = await asyncio.to_thread(_remove_dirs, orphans)
    report += await asyncio.to_thread(_remove_old_files, data / "downloads", expired_before)
    report += await asyncio.to_thread(_remove_old_files, data / "cache", expired_before)

    logger.info(
        "cleanup: removed %d job folders and %d files, freed %.1f MB",
        report.jobs_removed,
        report.files_removed,
        report.bytes_freed / 1e6,
    )
    return report
