import functools
import os
import shutil
import socket
import sys
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from clippers.cli import app
from clippers.ingest import DownloadError, download, is_url
from tests.media import probe_duration, probe_size, requires_ffmpeg


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass  # keep test output clean


class _QuietServer(ThreadingHTTPServer):
    def handle_error(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> None:
        # yt-dlp probes a URL by reading its first bytes and hanging up. That's expected;
        # anything else is a real error and should still be printed.
        if not isinstance(sys.exception(), (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


@pytest.fixture
def video_server(sample_video: Path, tmp_path: Path) -> Iterator[str]:
    """Serve sample_video at http://127.0.0.1:<port>/sample.mp4. Yields the base URL."""
    root = tmp_path / "served"
    root.mkdir()
    shutil.copy(sample_video, root / "sample.mp4")

    handler = functools.partial(_QuietHandler, directory=str(root))
    server = _QuietServer(("127.0.0.1", 0), handler)  # port 0 = any free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("http://cdn.example.com/stream.mp4", True),
        ("stream.mp4", False),
        ("/Users/me/stream.mp4", False),
        ("file:///etc/passwd", False),
        ("ftp://example.com/x.mp4", False),
        ("https://", False),
    ],
)
def test_is_url(value: str, expected: bool) -> None:
    assert is_url(value) is expected


@requires_ffmpeg
def test_download_direct_link(video_server: str, tmp_path: Path) -> None:
    dest = tmp_path / "downloads"

    path = download(f"{video_server}/sample.mp4", dest)

    assert path.parent == dest
    assert path.suffix == ".mp4"
    assert probe_duration(path) == pytest.approx(10.0, abs=0.1)


@requires_ffmpeg
def test_download_same_url_twice_reuses_file(video_server: str, tmp_path: Path) -> None:
    url = f"{video_server}/sample.mp4"
    first = download(url, tmp_path)
    before = first.stat()
    os.utime(first, (before.st_atime - 86_400, before.st_mtime - 86_400))  # "a day old"

    second = download(url, tmp_path)

    after = second.stat()
    assert second == first
    assert after.st_ino == before.st_ino  # same file on disk: not downloaded again
    assert after.st_mtime > before.st_mtime - 86_400  # but marked as just used (cleanup)


def test_download_404_raises(video_server: str, tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="could not download"):
        download(f"{video_server}/missing.mp4", tmp_path)


def test_download_rejects_non_http(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not an http"):
        download("file:///etc/passwd", tmp_path)


@requires_ffmpeg
def test_cli_cut_accepts_url(
    video_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # downloads/ is relative to cwd; keep it out of the repo
    out = tmp_path / "clip.mp4"

    result = CliRunner().invoke(
        app,
        [
            "cut",
            "--no-captions",
            f"{video_server}/sample.mp4",
            "-s",
            "0:02",
            "-d",
            "1",
            "-o",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert probe_size(out) == (1080, 1920)
    assert (tmp_path / "downloads").is_dir()
