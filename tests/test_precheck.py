from precheck import parse_ffprobe_duration, video_duration, check


def test_parse_duration():
    assert parse_ffprobe_duration("2618.53\n") == 2618.53


def test_video_duration_uses_runner():
    assert video_duration("x.mp4", runner=lambda path: "12.0\n") == 12.0


def test_check_blocks_long_unverified():
    ok, reason = check(2618.0, verified=False, allow_long=False)
    assert ok is False and "too long" in reason.lower()


def test_check_allows_short():
    assert check(600.0, verified=False, allow_long=False) == (True, "")


def test_check_allows_long_when_verified():
    assert check(2618.0, verified=True, allow_long=False) == (True, "")


def test_check_allows_long_with_override():
    assert check(2618.0, verified=False, allow_long=True) == (True, "")
