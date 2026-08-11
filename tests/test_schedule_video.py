import pytest

from schedule_video import (display_date, display_time, parse_args,
                            wait_for_edit_surface, wait_for_save_landed)


class DelayedLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def count(self):
        return int(self.selector == "#title-textarea #textbox" and self.page.waits >= 2)


class DelayedEditPage:
    def __init__(self):
        self.waits = 0

    def locator(self, selector):
        return DelayedLocator(self, selector)

    async def wait_for_timeout(self, _timeout_ms):
        self.waits += 1


@pytest.mark.asyncio
async def test_wait_for_edit_surface_allows_studio_to_mount():
    page = DelayedEditPage()

    locator = await wait_for_edit_surface(page, timeout_ms=2_000)

    assert locator.selector == "#title-textarea #textbox"
    assert page.waits == 2


class SavedButton:
    async def is_disabled(self):
        return True

    async def is_visible(self):
        return True


@pytest.mark.asyncio
async def test_wait_for_save_landed_accepts_disabled_save(monkeypatch):
    page = DelayedEditPage()

    async def no_saving_text(_page):
        return "Video details"

    monkeypatch.setattr("schedule_video.ui.all_text", no_saving_text)

    assert await wait_for_save_landed(page, SavedButton(), timeout_ms=2_000)


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
