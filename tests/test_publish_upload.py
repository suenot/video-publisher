import pytest

from publish import (details_validation_issues, format_validation_issues, save,
                     _fill_upload_contenteditable, _upload_route,
                     _wait_for_upload_launcher)


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


class ContenteditableKeyboard:
    async def press(self, _keys):
        return None

    async def insert_text(self, _value):
        return None

    async def type(self, _value, delay=0):
        return None


class ContenteditablePage:
    def __init__(self):
        self.keyboard = ContenteditableKeyboard()

    async def wait_for_timeout(self, _timeout_ms):
        return None

    async def evaluate(self, _script):
        return None


class PolymerContenteditable:
    def __init__(self):
        self.value = ""

    async def scroll_into_view_if_needed(self, timeout=0):
        return None

    async def click(self, timeout=0):
        return None

    async def focus(self, timeout=0):
        return None

    async def fill(self, _value):
        return None

    async def inner_text(self):
        return self.value

    async def evaluate(self, _script, value):
        self.value = value
        return True


@pytest.mark.asyncio
async def test_contenteditable_uses_polymer_input_fallback():
    field = PolymerContenteditable()

    assert await _fill_upload_contenteditable(
        ContenteditablePage(), field, "Описание", "description") is True
    assert field.value == "Описание"


class MustNotClickSavePage:
    def locator(self, _selector):
        raise AssertionError("Save control must not be queried")


@pytest.mark.asyncio
async def test_save_stops_before_button_when_form_is_invalid(monkeypatch):
    async def invalid(_page, _debug, action):
        assert action == "Save"
        return False

    monkeypatch.setattr("publish.validate_details_before_action", invalid)

    assert await save(MustNotClickSavePage(), debug=False) is False
