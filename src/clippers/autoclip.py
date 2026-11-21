"""The whole pipeline as library functions: video in, clips out.

Used by the CLI (`clippers detect` / `auto`) and by the API worker. Everything here
reports problems by raising exceptions; deciding how to show them (exit codes, HTTP
statuses, job states) is the caller's job.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clippers.ai import AIMoment, OpenAISuggester, suggest_moments
from clippers.batch import ClipOutcome, run_batch
from clippers.detect import detect_moments
from clippers.framing import Framing
from clippers.ingest import DEFAULT_DOWNLOAD_DIR, resolve_source
from clippers.moments import MomentsFile, save_moments
from clippers.pipeline import CaptionOptions
from clippers.transcribe import DEFAULT_MODEL, Transcript, transcribe_cached

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]
"""Called with a short stage name ("downloading", "transcribing", ...) as work moves on."""


def _ignore(stage: str) -> None:
    pass


@dataclass(frozen=True, slots=True)
class AutoOptions:
    count: int = 5
    duration: int = 30
    framing: Framing = Framing.BLUR
    captions: bool = True
    use_transcript: bool = True
    whisper_model: str = DEFAULT_MODEL
    language: str | None = None
    use_ai: bool = False
    ai_model: str | None = None

    def __post_init__(self) -> None:
        # Runs after the generated __init__: the dataclass's place for validation.
        if self.use_ai and not self.use_transcript:
            raise ValueError(
                "AI scoring needs the transcript, so it can't run with the transcript off"
            )


@dataclass(frozen=True, slots=True)
class Detection:
    source: Path  # the local video file (downloaded if a URL was given)
    plan: MomentsFile
    transcript: Transcript | None


@dataclass(frozen=True, slots=True)
class AutoResult:
    plan: MomentsFile
    moments_path: Path
    outcomes: list[ClipOutcome]


def find_moments(
    video: str,
    options: AutoOptions,
    *,
    download_dir: Path = DEFAULT_DOWNLOAD_DIR,
    progress: Progress = _ignore,
) -> Detection:
    """Fetch, transcribe (cached), ask the AI (cached, optional) and score."""
    progress("downloading")
    source = resolve_source(video, dest_dir=download_dir)
    if not source.is_file():  # check early, so every caller gets the same clear message
        raise FileNotFoundError(f"source video not found: {source}")

    transcript = None
    if options.use_transcript:
        progress("transcribing")
        transcript = transcribe_cached(
            source, model=options.whisper_model, language=options.language
        )

    ai_moments: list[AIMoment] = []
    if options.use_ai and transcript is not None:
        progress("asking AI")
        ai_moments = suggest_moments(
            transcript,
            OpenAISuggester(options.ai_model),
            max_moments=max(10, options.count * 2),
        )

    progress("detecting")
    plan = detect_moments(
        video,
        source,
        count=options.count,
        duration=options.duration,
        transcript=transcript,
        ai_moments=ai_moments,
    )
    return Detection(source=source, plan=plan, transcript=transcript)


def render_clips(
    detection: Detection,
    out_dir: Path,
    options: AutoOptions,
    *,
    progress: Progress = _ignore,
) -> AutoResult:
    """Save the plan as moments.json in `out_dir` and render every moment there."""
    plan = detection.plan.model_copy(
        update={"framing": options.framing, "captions": options.captions}
    )
    moments_path = save_moments(plan, out_dir / "moments.json")
    caption_options = (
        CaptionOptions(model=options.whisper_model, language=options.language)
        if options.captions
        else None
    )
    progress("rendering")
    outcomes = run_batch(
        plan,
        detection.source,
        out_dir,
        captions=caption_options,
        transcript=detection.transcript,
    )
    return AutoResult(plan=plan, moments_path=moments_path, outcomes=outcomes)


def auto_clip(
    video: str,
    out_dir: Path,
    options: AutoOptions,
    *,
    download_dir: Path = DEFAULT_DOWNLOAD_DIR,
    progress: Progress = _ignore,
) -> AutoResult:
    """Video (path or URL) in, finished clips in `out_dir` out."""
    detection = find_moments(video, options, download_dir=download_dir, progress=progress)
    return render_clips(detection, out_dir, options, progress=progress)
