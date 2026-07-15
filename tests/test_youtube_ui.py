import pytest
from youtube_ui import verify_gate_present, all_text


class FakePage:
    def __init__(self, text):
        self._text = text

    async def evaluate(self, js):
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
