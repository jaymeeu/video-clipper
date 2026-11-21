"""Command-line interface.

The only module that configures logging or writes to the terminal. Everything else
raises exceptions and emits log records; this layer decides how users see them.
"""

import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from clippers.batch import run_batch
from clippers.framing import Framing
from clippers.ingest import DEFAULT_DOWNLOAD_DIR, DownloadError, download, resolve_source
from clippers.moments import load_moments
from clippers.pipeline import CaptionOptions, make_clip
from clippers.timecode import parse_timestamp
from clippers.transcribe import DEFAULT_MODEL
from clippers.video import FFmpegError

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Auto-highlight clipper: turn stream recordings into vertical clips.",
    no_args_is_help=True,
    add_completion=False,
)

# Options shared by several commands: define once, reuse as a type.
ModelOption = Annotated[
    str,
    typer.Option(
        "--model", "-m", help="Whisper model: tiny, base, small, medium, large-v3, turbo."
    ),
]
LanguageOption = Annotated[
    str | None,
    typer.Option("--language", "-l", help="Spoken language code, e.g. en. Default: detect."),
]


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show debug logs, including ffmpeg commands.")
    ] = False,
) -> None:
    """Global options, applied before any subcommand runs."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,  # replace any handlers left over from a previous config
    )


@app.command("download")
def download_command(
    url: Annotated[str, typer.Argument(help="Video URL: a direct file link or a platform page.")],
    dest_dir: Annotated[
        Path, typer.Option("--dir", help="Where to save downloads.")
    ] = DEFAULT_DOWNLOAD_DIR,
) -> None:
    """Download a video from URL without cutting it (to cut it several times later)."""
    try:
        path = download(url, dest_dir)
    except (DownloadError, ValueError) as e:
        _fail(str(e))

    typer.echo(path)


@app.command()
def cut(
    video: Annotated[str, typer.Argument(help="Source video: a local file or an http(s) URL.")],
    start: Annotated[str, typer.Option("--start", "-s", help="Start time: SS, MM:SS or HH:MM:SS.")],
    duration: Annotated[float, typer.Option("--duration", "-d", help="Clip length (s).")] = 30.0,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output file.")] = Path(
        "output/clip.mp4"
    ),
    framing: Annotated[
        Framing,
        typer.Option(
            "--framing",
            "-f",
            case_sensitive=False,
            help="blur: whole frame on a blurred 9:16 background. "
            "crop: fill 9:16, cut the sides. original: no reframing.",
        ),
    ] = Framing.BLUR,
    captions: Annotated[
        bool, typer.Option("--captions/--no-captions", help="Transcribe and burn in captions.")
    ] = True,
    model: ModelOption = DEFAULT_MODEL,
    language: LanguageOption = None,
) -> None:
    """Cut a single clip from VIDEO (file or URL) at a given timestamp."""
    try:
        start_seconds = parse_timestamp(start)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="'--start'") from e

    caption_options = CaptionOptions(model=model, language=language) if captions else None
    try:
        source = resolve_source(video)
        result = make_clip(
            source,
            output,
            start=start_seconds,
            duration=duration,
            framing=framing,
            captions=caption_options,
        )
    except FFmpegError as e:
        logger.debug("ffmpeg stderr:\n%s", e.stderr)
        _fail(str(e))
    except (DownloadError, FileNotFoundError, ValueError) as e:
        _fail(str(e))

    if result.transcript is not None:
        logger.info("transcript: %s", result.transcript.text or "(no speech)")
    typer.echo(result.path)  # stdout: just the path, so scripts can capture it


@app.command()
def batch(
    moments_file: Annotated[Path, typer.Argument(help="JSON file listing the moments to clip.")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Default: output/<moments file name>/"),
    ] = None,
    model: ModelOption = DEFAULT_MODEL,
    language: LanguageOption = None,
) -> None:
    """Make one clip per moment in MOMENTS_FILE. Failed clips don't stop the others."""
    try:
        plan = load_moments(moments_file)
        source = resolve_source(plan.source, base_dir=moments_file.parent)
    except (DownloadError, ValueError) as e:
        _fail(str(e))

    out_dir = output_dir or Path("output") / moments_file.stem
    caption_options = CaptionOptions(model=model, language=language) if plan.captions else None
    outcomes = run_batch(plan, source, out_dir, captions=caption_options)

    for outcome in outcomes:
        if outcome.path is not None:
            typer.echo(outcome.path)  # stdout: one path per finished clip

    failed = [o for o in outcomes if not o.ok]
    typer.echo(f"{len(outcomes) - len(failed)}/{len(outcomes)} clips made in {out_dir}", err=True)
    if failed:
        for outcome in failed:
            typer.secho(f"  #{outcome.number} failed: {outcome.error}", fg="red", err=True)
        raise typer.Exit(code=1)


def _fail(message: str) -> NoReturn:
    """Print an error to stderr and exit 1. Users never see a traceback."""
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)
