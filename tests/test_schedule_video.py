import pytest

from schedule_video import display_date, display_time, parse_args


def test_display_date_matches_studio():
    assert display_date("2026-08-03") == "Aug 3, 2026"


@pytest.mark.parametrize(("value", "expected"), [
    ("17:00", "5:00 PM"),
    ("5:00 pm", "5:00 PM"),
    ("00:00", "12:00 AM"),
])
def test_display_time_matches_studio(value, expected):
    assert display_time(value) == expected


def test_display_time_rejects_invalid_value():
    with pytest.raises(ValueError, match="time must be"):
        display_time("5pm")


def test_channel_is_required():
    with pytest.raises(SystemExit):
        parse_args([
            "--video-id", "eMyNgN7y_VQ",
            "--date", "2026-08-03",
            "--time", "5:00 PM",
        ])


def test_video_id_may_start_with_dash():
    args = parse_args([
        "--channel-handle", "@marketmaker-cc",
        "--video-id", "-LnB6i7vcH8",
        "--date", "2026-08-08",
        "--time", "5:00 PM",
    ])
    assert args.video_id == "-LnB6i7vcH8"
