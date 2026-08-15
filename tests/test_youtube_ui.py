import pytest
from youtube_ui import all_text, first_visible, verify_gate_present


class FakePage:
    def __init__(self, text):
        self._text = text

    async def evaluate(self, _js):
        return self._text


@pytest.mark.asyncio
async def test_all_text_returns_evaluate():
    assert await all_text(FakePage("hello")) == "hello"


@pytest.mark.asyncio
async def test_gate_detected_straight_apostrophe():
    assert await verify_gate_present(FakePage("please verify it's you now")) is True


@pytest.mark.asyncio
async def test_gate_detected_curly_apostrophe():
    assert await verify_gate_present(FakePage("verify it’s you")) is True


@pytest.mark.asyncio
async def test_gate_absent():
    assert await verify_gate_present(FakePage("channel dashboard")) is False


class Candidate:
    def __init__(self, visible):
        self.visible = visible

    async def is_visible(self):
        return self.visible


class Candidates:
    def __init__(self, items):
        self.items = items

    async def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class DuplicateFieldPage:
    def __init__(self):
        self.hidden = Candidate(False)
        self.visible = Candidate(True)
        self.waits = 0

    def locator(self, _selector):
        return Candidates([self.hidden, self.visible])

    async def wait_for_timeout(self, _timeout_ms):
        self.waits += 1


@pytest.mark.asyncio
async def test_first_visible_skips_hidden_field_behind_modal():
    page = DuplicateFieldPage()

    field = await first_visible(page, ["#title-textarea #textbox"], 1000)

    assert field is page.visible
    assert page.waits == 0
