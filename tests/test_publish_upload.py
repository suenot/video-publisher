import pytest

from publish import _wait_for_upload_launcher


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
