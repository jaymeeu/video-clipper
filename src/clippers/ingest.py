"""Fetch source videos from URLs: direct file links or platform pages, via yt-dlp."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_DIR = Path("downloads")

# Our output is 1080 wide, so anything above 1080p is wasted bandwidth and decode time.
# Prefer H.264 + AAC (merge into MP4 cleanly), fall back to whatever exists.
_FORMAT = (
    "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]"
    "/bv*[height<=1080]+ba"
    "/b[height<=1080]"
    "/b"
)  # fmt: skip


class DownloadError(RuntimeError):
    """The video at a URL could not be fetched."""


class _YtDlpLogger:
    """Route yt-dlp's console output into our logging instead of stdout.

    yt-dlp accepts any object with these methods (duck typing); the signatures match
    the logger Protocol in yt-dlp's type stubs, so pyright can verify it structurally.
    Errors go to DEBUG because we re-raise them as DownloadError; logging them
    here as well would print every failure twice.
    """

    def __init__(self, ydl: object | None = None) -> None:
        pass

    def debug(self, message: str) -> None:
        logger.debug(message)

    def info(self, message: str) -> None:
        logger.debug(message)

    def warning(self, message: str, *, once: bool = False, only_once: bool = False) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.debug(message)

    def stdout(self, message: str) -> None:
        logger.debug(message)

    def stderr(self, message: str) -> None:
        logger.debug(message)


def is_url(value: str) -> bool:
    """True for http(s) URLs. Everything else is treated as a local path."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def download(url: str, dest_dir: Path = DEFAULT_DOWNLOAD_DIR) -> Path:
    """Download the video at `url` into `dest_dir` and return the local file path.

    Works for direct links (…/stream.mp4) and any site yt-dlp supports. Files are
    named by source and ID, so downloading the same URL twice reuses the first file.

    Raises:
        ValueError: if `url` is not an http(s) URL.
        DownloadError: if the video can't be fetched.
    """
    if not is_url(url):
        raise ValueError(f"not an http(s) URL: {url!r}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    logger.info("fetching %s", url)
    try:
        # Options passed inline so the type checker validates every key against
        # yt-dlp's own TypedDict: a misspelt option becomes a type error, not a no-op.
        with yt_dlp.YoutubeDL(
            {
                "format": _FORMAT,
                "merge_output_format": "mp4",
                "outtmpl": str(dest_dir / "%(extractor)s-%(id)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "noprogress": True,
                "logger": _YtDlpLogger(),
                "js_runtimes": {"deno": {}, "node": {}},  # YouTube needs a JS runtime
            }
        ) as ydl:
            info = ydl.extract_info(url, download=True)
    except YtDlpDownloadError as e:
        reason = str(e).removeprefix("ERROR: ")
        raise DownloadError(f"could not download {url}: {reason}") from e

    # yt-dlp's info dict is loosely typed (dict[str, Any]); pin down the one field we use.
    downloads: list[dict[str, Any]] = (info or {}).get("requested_downloads") or []
    if not downloads:
        raise DownloadError(f"no downloadable video found at {url}")

    path = Path(str(downloads[0]["filepath"]))
    logger.info("downloaded -> %s", path)
    return path
