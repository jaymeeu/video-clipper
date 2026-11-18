import pytest

from clippers.timecode import parse_timestamp


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0.0),
        ("83", 83.0),
        ("83.5", 83.5),
        ("1:23", 83.0),
        ("01:23.25", 83.25),
        ("0:05", 5.0),
        ("1:02:03", 3723.0),
        ("10:00:00", 36000.0),
        ("  1:23  ", 83.0),  # surrounding whitespace is tolerated
    ],
)
def test_parse_timestamp_valid(value: str, expected: float) -> None:
    assert parse_timestamp(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "abc",
        "1:2x",
        "-5",  # negative
        "1:-5",
        "1:60",  # seconds must be < 60 once there's a minutes part
        "1:60:00",  # same for minutes once there's an hours part
        "1:2:3:4",  # too many parts
        ":30",  # empty part
        "1:",
        "1.5:30",  # only the seconds part may be fractional
        "nan",  # float("nan") parses! must still be rejected
        "inf",
    ],
)
def test_parse_timestamp_invalid_raises(value: str) -> None:
    with pytest.raises(ValueError, match="invalid timestamp"):
        parse_timestamp(value)
