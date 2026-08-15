import pytest

import finish_draft


class DraftButton:
    @property
    def first(self):
        return self

    async def count(self):
        return 1


class DelayedDraftPage:
    def __init__(self):
        self.waits = 0
        self.button = DraftButton()

    def locator(self, selector):
        assert selector == finish_draft.DRAFT_BANNER_SELECTOR
        return self.button

    async def wait_for_timeout(self, _timeout_ms):
        self.waits += 1


@pytest.mark.asyncio
async def test_wait_for_draft_banner_handles_late_studio_mount(monkeypatch):
    page = DelayedDraftPage()

    async def delayed_text(_page):
        return "this video is in a draft state" if page.waits >= 2 else "loading"

    monkeypatch.setattr(finish_draft.ui, "all_text", delayed_text)

    button = await finish_draft.wait_for_draft_banner(page, timeout_ms=2_000)

    assert button is page.button
    assert page.waits == 2
