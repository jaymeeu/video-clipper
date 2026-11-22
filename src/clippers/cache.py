"""A small on-disk cache for expensive results (transcripts, AI suggestions).

Each entry is one JSON file holding a pydantic model, named by a hash of whatever
determines the result. Entries are written atomically and unreadable ones are treated
as missing, so the cache can only ever save time, never break a run.
"""

import hashlib
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def cache_dir() -> Path:
    """Where clippers keeps cached results. Override with the CLIPPERS_CACHE_DIR env var.

    Read at call time, not import time, so tests (and users) can change it per run.
    """
    return Path(os.environ.get("CLIPPERS_CACHE_DIR") or Path.home() / ".cache" / "clippers")


def cache_path(kind: str, *identity: str) -> Path:
    """The cache file for a result of `kind` determined by the `identity` strings."""
    key = hashlib.sha256("|".join(identity).encode()).hexdigest()[:24]
    return cache_dir() / kind / f"{key}.json"


def load[M: BaseModel](path: Path, model: type[M]) -> M | None:
    """The cached value at `path`, or None if it's missing or unreadable.

    A hit refreshes the file's modification time, so cleanup (which removes entries by
    age) treats it as "recently used" rather than "created long ago".
    """
    if not path.is_file():
        return None
    try:
        value = model.model_validate_json(path.read_bytes())
    except ValidationError:
        logger.warning("ignoring unreadable cache file %s", path)
        return None
    path.touch()
    return value


def save(path: Path, value: BaseModel) -> None:
    """Write `value` to `path` atomically.

    Write to a temp file, then rename: a crash mid-write can't leave a half-written file
    that a later run would trust. (A rename on the same disk is atomic.)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value.model_dump_json(), encoding="utf-8")
    tmp.replace(path)
