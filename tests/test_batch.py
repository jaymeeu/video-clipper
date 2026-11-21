import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from clippers.batch import run_batch
from clippers.cli import app
from clippers.moments import MomentsFile
from clippers.pipeline import make_clip
from tests.media import probe_duration, probe_size

# sample_video is 10s long.


def plan_for(source: Path, *moments: dict[str, object]) -> MomentsFile:
    return MomentsFile.model_validate(
        {"source": str(source), "captions": False, "moments": list(moments)}
    )


class TestFitToVideo:
    def test_clip_running_past_end_is_shortened(
        self, sample_video: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        result = make_clip(sample_video, tmp_path / "c.mp4", start=8.0, duration=5.0)

        assert probe_duration(result.path) == pytest.approx(2.0, abs=0.1)
        # ffmpeg alone also yields 2s, silently; what we add is noticing and saying so.
        assert "shortened 5.0s -> 2.0s" in caplog.text

    def test_clip_starting_past_end_is_rejected(self, sample_video: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="past the end of the video"):
            make_clip(sample_video, tmp_path / "c.mp4", start=30.0, duration=5.0)


class TestRunBatch:
    def test_makes_one_named_clip_per_moment(self, sample_video: Path, tmp_path: Path) -> None:
        plan = plan_for(
            sample_video,
            {"start": "0:01", "duration": 2, "title": "First one"},
            {"start": 5, "duration": 1},
        )

        outcomes = run_batch(plan, sample_video, tmp_path / "out", captions=None)

        assert [o.ok for o in outcomes] == [True, True]
        assert [o.path.name for o in outcomes if o.path] == ["01-first-one.mp4", "02-0m05s.mp4"]
        assert all(probe_size(o.path) == (1080, 1920) for o in outcomes if o.path)

    def test_failed_clip_does_not_stop_the_batch(self, sample_video: Path, tmp_path: Path) -> None:
        plan = plan_for(
            sample_video,
            {"start": 1, "duration": 1},
            {"start": 60, "duration": 1},  # past the end of a 10s video
            {"start": 3, "duration": 1},
        )

        outcomes = run_batch(plan, sample_video, tmp_path / "out", captions=None)

        assert [o.ok for o in outcomes] == [True, False, True]
        assert outcomes[1].error is not None
        assert "past the end" in outcomes[1].error
        assert outcomes[1].path is None


class TestBatchCli:
    def test_source_path_is_relative_to_moments_file(
        self, sample_video: Path, tmp_path: Path
    ) -> None:
        project = tmp_path / "stream-42"
        project.mkdir()
        shutil.copy(sample_video, project / "recording.mp4")
        moments = project / "moments.json"
        moments.write_text(
            json.dumps(
                {
                    "source": "recording.mp4",  # next to the JSON, not the cwd
                    "captions": False,
                    "moments": [{"start": 1, "duration": 1}, {"start": 4, "duration": 1}],
                }
            )
        )
        out = tmp_path / "clips"

        result = CliRunner().invoke(app, ["batch", str(moments), "-o", str(out)])

        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines() == [str(out / "01-0m01s.mp4"), str(out / "02-0m04s.mp4")]
        assert "2/2 clips made" in result.stderr

    def test_partial_failure_exits_1_and_lists_failures(
        self, sample_video: Path, tmp_path: Path
    ) -> None:
        moments = tmp_path / "m.json"
        moments.write_text(
            json.dumps(
                {
                    "source": str(sample_video),
                    "captions": False,
                    "moments": [{"start": 1, "duration": 1}, {"start": 99}],
                }
            )
        )

        result = CliRunner().invoke(app, ["batch", str(moments), "-o", str(tmp_path / "o")])

        assert result.exit_code == 1
        assert len(result.stdout.splitlines()) == 1  # the clip that worked
        assert "1/2 clips made" in result.stderr
        assert "#2 failed" in result.stderr

    def test_invalid_moments_file_fails_before_any_work(self, tmp_path: Path) -> None:
        moments = tmp_path / "m.json"
        moments.write_text(json.dumps({"source": "x.mp4", "moments": [{"start": "nope"}]}))

        result = CliRunner().invoke(app, ["batch", str(moments)])

        assert result.exit_code == 1
        assert "moments[0].start: invalid timestamp" in result.stderr
        assert "Traceback" not in result.output
