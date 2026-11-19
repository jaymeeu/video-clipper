"""Command-line interface.

The only module that configures logging or writes to the terminal. Everything else
raises exceptions and emits log records; this layer decides how users see them.
"""

import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from clippers.framing import Framing
from clippers.timecode import parse_timestamp
from clippers.video import FFmpegError, cut_clip

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Auto-highlight clipper: turn stream recordings into vertical clips.",
    no_args_is_help=True,
    add_completion=False,
)


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


@app.command()
def cut(
    video: Annotated[Path, typer.Argument(help="Source video file.")],
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
) -> None:
    """Cut a single clip from VIDEO at a given timestamp."""
    try:
        start_seconds = parse_timestamp(start)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="'--start'") from e

    try:
        clip = cut_clip(video, output, start=start_seconds, duration=duration, framing=framing)
    except FFmpegError as e:
        logger.debug("ffmpeg stderr:\n%s", e.stderr)
        _fail(str(e))
    except (FileNotFoundError, ValueError) as e:
        _fail(str(e))

    typer.echo(clip)  # stdout: just the path, so scripts can capture it


def _fail(message: str) -> NoReturn:
    """Print a one-line error to stderr and exit 1. Users never see a traceback."""
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)
