import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from clippers.batch import clip_filename, slugify
from clippers.framing import Framing
from clippers.moments import Moment, MomentsFile, MomentsFileError, load_moments


def write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data))
    return path


class TestMomentsModel:
    def test_start_accepts_timestamps_and_numbers(self) -> None:
        plan = MomentsFile.model_validate(
            {"source": "x.mp4", "moments": [{"start": "1:23"}, {"start": 83.5}, {"start": "90"}]}
        )

        assert [m.start for m in plan.moments] == [83.0, 83.5, 90.0]

    def test_defaults(self) -> None:
        plan = MomentsFile.model_validate({"source": "x.mp4", "moments": [{"start": 0}]})

        assert plan.framing is Framing.BLUR
        assert plan.captions is True
        assert plan.moments[0].duration == 30.0
        assert plan.moments[0].title is None

    @pytest.mark.parametrize(
        "moment",
        [
            {"start": "1:60"},  # bad timestamp
            {"start": -5},  # negative
            {"start": 0, "duration": 0},
            {"start": 0, "duration": 601},  # longer than any platform allows
            {"start": 0, "strat": 3},  # typo'd key
            {},  # missing start
        ],
    )
    def test_invalid_moments_rejected(self, moment: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            MomentsFile.model_validate({"source": "x.mp4", "moments": [moment]})

    def test_needs_at_least_one_moment(self) -> None:
        with pytest.raises(ValidationError):
            MomentsFile.model_validate({"source": "x.mp4", "moments": []})


class TestLoadMoments:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        path = write_json(
            tmp_path / "m.json",
            {"source": "x.mp4", "framing": "crop", "moments": [{"start": "0:10"}]},
        )

        plan = load_moments(path)

        assert plan.framing is Framing.CROP
        assert plan.moments[0].start == 10.0

    def test_reports_every_problem_with_location(self, tmp_path: Path) -> None:
        path = write_json(
            tmp_path / "m.json",
            {"source": "x.mp4", "captons": False, "moments": [{"start": 1}, {"start": "1:60"}]},
        )

        with pytest.raises(MomentsFileError) as exc_info:
            load_moments(path)

        message = str(exc_info.value)
        assert "2 problem(s)" in message
        assert "moments[1].start: invalid timestamp: '1:60'" in message
        assert "captons: Extra inputs are not permitted" in message

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text('{"source": "x.mp4", "moments": [')

        with pytest.raises(MomentsFileError, match="Invalid JSON"):
            load_moments(path)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(MomentsFileError, match="not found"):
            load_moments(tmp_path / "nope.json")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The Robot Hand Reveal!", "the-robot-hand-reveal"),
        ("Ọmọ dey vibe 🔥🔥", "omo-dey-vibe"),
        ("  --weird//chars**  ", "weird-chars"),
        ("🔥🔥🔥", ""),
        ("a" * 80, "a" * 50),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (Moment(start=83, title="Robot hand"), "03-robot-hand.mp4"),
        (Moment(start=83), "03-1m23s.mp4"),
        (Moment(start=83, title="🔥🔥"), "03-1m23s.mp4"),  # title with no usable characters
    ],
)
def test_clip_filename(moment: Moment, expected: str) -> None:
    assert clip_filename(3, moment) == expected
