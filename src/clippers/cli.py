"""Command-line interface.

The only module that configures logging or writes to the terminal. Everything else
raises exceptions and emits log records; this layer decides how users see them.
"""

import logging
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from dotenv import find_dotenv, load_dotenv

from clippers.ai import (
    AIScoringError,
)
from clippers.autoclip import AutoOptions, Detection, find_moments, render_clips
from clippers.batch import ClipOutcome, run_batch
from clippers.framing import Framing
from clippers.ingest import DEFAULT_DOWNLOAD_DIR, DownloadError, download, resolve_source
from clippers.logs import configure_logging
from clippers.moments import MomentsFile, load_moments, save_moments
from clippers.pipeline import CaptionOptions, make_clip
from clippers.timecode import format_timestamp, parse_timestamp
from clippers.transcribe import (
    DEFAULT_MODEL,
    load_cached_transcript,
)
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
    configure_logging(verbose=verbose)
    load_env_file()


def load_env_file() -> Path | None:
    """Load settings like OPENAI_API_KEY from a .env file, if there is one.

    Searches the current folder, then its parents (usecwd=True; the default would search
    from this file's folder inside the installed package). Variables already set in the
    environment win over the file (override=False), so a real `export` always takes
    precedence. Returns the file used, for logging and tests.
    """
    found = find_dotenv(usecwd=True)
    if not found:
        return None
    load_dotenv(found, override=False)
    logger.debug("loaded settings from %s", found)  # never log the values themselves
    return Path(found)


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


# Options shared by detect and auto.
CountOption = Annotated[
    int, typer.Option("--count", "-n", min=1, max=50, help="Maximum moments to pick.")
]
DurationOption = Annotated[
    int, typer.Option("--duration", "-d", min=5, max=600, help="Typical clip length (s).")
]
TranscriptOption = Annotated[
    bool,
    typer.Option(
        "--transcript/--no-transcript",
        help="Also score speech and reactions (transcribes once, then cached).",
    ),
]
AIOption = Annotated[
    bool,
    typer.Option(
        "--ai/--no-ai",
        help="Also ask an AI model which moments are clip-worthy. Sends the transcript "
        "to OpenAI and costs a few cents per video (cached afterwards). Needs OPENAI_API_KEY.",
    ),
]
AIModelOption = Annotated[
    str | None,
    typer.Option(
        "--ai-model", help="OpenAI model for --ai. Default: $CLIPPERS_AI_MODEL or gpt-5-mini."
    ),
]


def _find_moments(video: str, options: AutoOptions) -> Detection:
    """autoclip.find_moments, with errors turned into clean CLI messages."""
    try:
        return find_moments(video, options)
    except FFmpegError as e:
        logger.debug("ffmpeg stderr:\n%s", e.stderr)
        _fail(str(e))
    except (AIScoringError, DownloadError, FileNotFoundError, ValueError) as e:
        _fail(str(e))


def _options(**kwargs: Any) -> AutoOptions:
    """AutoOptions from CLI flags; a bad combination is a usage error (exit 2)."""
    try:
        return AutoOptions(**kwargs)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


def _print_picks(plan: MomentsFile) -> None:
    for rank, moment in enumerate(plan.moments, start=1):
        typer.echo(
            f"  #{rank}  {format_timestamp(moment.start):>7}  score {moment.score or 0:4.2f}  "
            f"{moment.reason}",
            err=True,
        )


def _report(outcomes: list[ClipOutcome], out_dir: Path) -> None:
    """Print finished clip paths (stdout) and a summary (stderr); exit 1 on any failure."""
    for outcome in outcomes:
        if outcome.path is not None:
            typer.echo(outcome.path)  # stdout: one path per finished clip

    failed = [o for o in outcomes if not o.ok]
    typer.echo(f"{len(outcomes) - len(failed)}/{len(outcomes)} clips made in {out_dir}", err=True)
    if failed:
        for outcome in failed:
            typer.secho(f"  #{outcome.number} failed: {outcome.error}", fg="red", err=True)
        raise typer.Exit(code=1)


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

    caption_options = CaptionOptions(model=model, language=language) if plan.captions else None
    transcript = None
    if caption_options is not None:
        # Reuse the whole-video transcript from `detect` if it's cached (same model and
        # language); otherwise each clip is transcribed on its own.
        transcript = load_cached_transcript(source, model=model, language=language)
        if transcript is not None:
            logger.info("captions come from the cached transcript: no re-transcribing")
    out_dir = output_dir or Path("output") / moments_file.stem
    _report(
        run_batch(plan, source, out_dir, captions=caption_options, transcript=transcript), out_dir
    )


@app.command()
def detect(
    video: Annotated[str, typer.Argument(help="Source video: a local file or an http(s) URL.")],
    count: CountOption = 5,
    duration: DurationOption = 30,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Moments file. Default: output/<video>.moments.json"),
    ] = None,
    use_transcript: TranscriptOption = True,
    model: ModelOption = DEFAULT_MODEL,
    language: LanguageOption = None,
    use_ai: AIOption = False,
    ai_model: AIModelOption = None,
) -> None:
    """Find the moments in VIDEO that stand out most and write them to a moments file."""
    options = _options(
        count=count,
        duration=duration,
        use_transcript=use_transcript,
        whisper_model=model,
        language=language,
        use_ai=use_ai,
        ai_model=ai_model,
    )
    found = _find_moments(video, options)
    path = save_moments(found.plan, output or Path("output") / f"{found.source.stem}.moments.json")
    _print_picks(found.plan)
    typer.echo(f"next: clippers batch {path}", err=True)
    typer.echo(path)  # stdout: just the path, so `clippers batch $(clippers detect ...)` works


@app.command()
def auto(
    video: Annotated[str, typer.Argument(help="Source video: a local file or an http(s) URL.")],
    count: CountOption = 5,
    duration: DurationOption = 30,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Default: output/<video name>/"),
    ] = None,
    framing: Annotated[
        Framing,
        typer.Option("--framing", "-f", case_sensitive=False, help="blur, crop or original."),
    ] = Framing.BLUR,
    captions: Annotated[
        bool, typer.Option("--captions/--no-captions", help="Burn in captions.")
    ] = True,
    use_transcript: TranscriptOption = True,
    model: ModelOption = DEFAULT_MODEL,
    language: LanguageOption = None,
    use_ai: AIOption = False,
    ai_model: AIModelOption = None,
) -> None:
    """Find the best moments in VIDEO and turn them into clips, in one go.

    Same as `detect` then `batch`. The chosen moments are also saved as moments.json in
    the output folder, so you can tweak them and re-render with `clippers batch`.
    """
    options = _options(
        count=count,
        duration=duration,
        framing=framing,
        captions=captions,
        use_transcript=use_transcript,
        whisper_model=model,
        language=language,
        use_ai=use_ai,
        ai_model=ai_model,
    )
    found = _find_moments(video, options)
    _print_picks(found.plan)
    out_dir = output_dir or Path("output") / found.source.stem
    result = render_clips(found, out_dir, options)
    logger.info(
        "moments saved to %s (edit it and run `clippers batch` to re-render)", result.moments_path
    )
    _report(result.outcomes, out_dir)


def _fail(message: str) -> NoReturn:
    """Print an error to stderr and exit 1. Users never see a traceback."""
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)
