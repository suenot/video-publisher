import pytest

from channel import channel_id_from_url, normalize_handle, wait_for_channel_context


def test_normalize_handle_adds_at():
    assert normalize_handle("marketmaker-cc") == "@marketmaker-cc"


def test_normalize_handle_from_url():
    assert normalize_handle("https://youtube.com/@marketmaker-cc") == "@marketmaker-cc"


def test_channel_id_from_url():
    u = "https://studio.youtube.com/channel/UCbPEVsO_M-axL0mylsoTADw/videos"
    assert channel_id_from_url(u) == "UCbPEVsO_M-axL0mylsoTADw"


def test_channel_id_from_url_none():
    assert channel_id_from_url("https://studio.youtube.com/") is None


class RedirectingPage:
    def __init__(self, urls):
        self.urls = iter(urls)
        self.url = next(self.urls)

    async def wait_for_timeout(self, _timeout_ms):
        self.url = next(self.urls, self.url)


@pytest.mark.asyncio
async def test_wait_for_channel_context_allows_studio_redirect():
    page = RedirectingPage([
        "https://studio.youtube.com/",
        "https://studio.youtube.com/",
        "https://studio.youtube.com/channel/UCtarget",
    ])

    assert await wait_for_channel_context(page, timeout_ms=2_000) == "UCtarget"
