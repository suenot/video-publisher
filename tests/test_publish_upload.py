import pytest

from publish import (details_validation_issues, format_validation_issues,
                     _upload_route, _wait_for_upload_launcher)


def test_upload_route_targets_channel_and_opens_dialog():
    assert _upload_route("UCtarget") == (
        "https://studio.youtube.com/channel/UCtarget/videos/upload?d=ud"
    )


class DelayedLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def count(self):
        return int(self.selector == "ytcp-icon-button#upload-icon")

    async def is_visible(self):
        return self.page.waits >= 2


class DelayedStudioPage:
    def __init__(self):
        self.waits = 0

    def locator(self, selector):
        return DelayedLocator(self, selector)

    async def wait_for_timeout(self, _timeout_ms):
        self.waits += 1


@pytest.mark.asyncio
async def test_wait_for_upload_launcher_allows_studio_to_mount():
    page = DelayedStudioPage()

    locator, opens_dialog = await _wait_for_upload_launcher(page, timeout_ms=2_000)

    assert locator.selector == "ytcp-icon-button#upload-icon"
    assert opens_dialog is True
    assert page.waits == 2


class ValidationPage:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def evaluate(self, _script):
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_details_validation_returns_invalid_and_red_fields():
    issues = [
        {"field": "Title", "reason": "invalid", "text": "Title is too long"},
        {"field": "Category", "reason": "visual-red", "text": "Select"},
    ]

    assert await details_validation_issues(ValidationPage(issues)) == issues
    assert format_validation_issues(issues) == (
        "Title [invalid]: Title is too long; Category [visual-red]: Select"
    )


@pytest.mark.asyncio
async def test_details_validation_fails_closed_when_dom_inspection_breaks():
    issues = await details_validation_issues(
        ValidationPage(error=RuntimeError("shadow root detached")))

    assert issues == [{
        "field": "details form",
        "reason": "inspection-failed",
        "text": "shadow root detached",
    }]
