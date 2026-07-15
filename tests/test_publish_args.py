from publish import parse_args


def test_defaults():
    a = parse_args(["--video", "v.mp4"])
    assert a.visibility == "private" and a.made_for_kids is False and a.allow_long is False


def test_channel_and_visibility():
    a = parse_args(["--video", "v.mp4", "--channel-handle", "@x", "--visibility", "public"])
    assert a.channel_handle == "@x" and a.visibility == "public"
