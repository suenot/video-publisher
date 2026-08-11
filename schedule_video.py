"""Schedule an existing private video from its YouTube Studio edit page."""

import argparse
import asyncio
import re
import sys
from datetime import datetime

from camoufox_session import (logged_in_youtube, log, make_camoufox,
                               prepare_page, shot)
from channel import resolve_channel_id, select_channel
import youtube_ui as ui


STUDIO = "https://studio.youtube.com"


def display_date(value):
    """Convert YYYY-MM-DD to the date text used by the English Studio UI."""
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def display_time(value):
    """Normalize 24-hour or 12-hour input to Studio's 12-hour form."""
    clean = value.strip().upper()
    for pattern in ("%I:%M %p", "%H:%M"):
        try:
            parsed = datetime.strptime(clean, pattern)
            return parsed.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            pass
    raise ValueError("time must be HH:MM or H:MM AM/PM")


async def dom_click(locator):
    """Click without moving the pointer and triggering an unrelated tooltip."""
    await locator.evaluate("""el => {
      const target = el.closest(
        'button, [role=button], tp-yt-paper-item, ytcp-button, ' +
        'ytcp-dropdown-trigger, ytcp-text-dropdown-trigger, ' +
        'ytcp-video-visibility'
      ) || el;
      target.click();
    }""")


async def first_visible(locators):
    for locator in locators:
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if await candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


async def wait_for_edit_surface(page, timeout_ms=30_000):
    """Wait until Studio mounts the video details form after navigation."""
    return await ui.first_present(page, (
        "#title-textarea #textbox",
        "ytcp-video-visibility",
        "ytcp-dropdown-trigger",
    ), timeout_ms)


async def wait_for_save_landed(page, save, timeout_ms=20_000):
    """Wait for Studio to finish persisting a details-page save."""
    await page.wait_for_timeout(2000)
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        text = await ui.all_text(page)
        try:
            done = await save.is_disabled() or not await save.is_visible()
        except Exception:
            done = True
        if done and "saving" not in text:
            return True
        await page.wait_for_timeout(500)
    return False


async def wait_for_public_visibility(page, timeout_ms=15_000):
    """Confirm the edit page reflects Public after saving."""
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        visibility = await first_visible((
            page.locator("ytcp-video-visibility").filter(has_text="Public"),
            page.locator("ytcp-dropdown-trigger").filter(has_text="Public"),
            page.get_by_text("Public", exact=True),
        ))
        if visibility is not None:
            return True
        await page.wait_for_timeout(500)
    return False


async def visible_field_dump(scope):
    return await scope.evaluate("""root => {
      const out = [];
      const seen = new Set();
      const walk = node => {
        for (const el of node.querySelectorAll('*')) {
          if (seen.has(el)) continue;
          seen.add(el);
          if (el.shadowRoot) walk(el.shadowRoot);
          const rect = el.getBoundingClientRect();
          if (!rect.width || !rect.height) continue;
          const tag = el.tagName.toLowerCase();
          if (tag === 'input' || tag === 'button' || tag.includes('dropdown')) {
            out.push({tag, id: el.id || '', value: el.value || '',
              placeholder: el.placeholder || '', aria: el.getAttribute('aria-label') || '',
              text: (el.innerText || '').trim().slice(0, 80)});
          }
        }
      };
      walk(root);
      return out;
    }""")


async def open_visibility_editor(page):
    """Open the edit page's inline Save or publish panel."""
    visibility = await first_visible((
        page.locator("ytcp-video-visibility").filter(has_text="Private"),
        page.locator("ytcp-video-visibility").filter(has_text="Scheduled"),
        page.locator("ytcp-dropdown-trigger").filter(has_text="Private"),
        page.locator("ytcp-dropdown-trigger").filter(has_text="Scheduled"),
        page.get_by_text("Private", exact=True),
        page.get_by_text("Scheduled", exact=True),
    ))
    if visibility is None:
        raise RuntimeError("video is not private/scheduled or Visibility control was not found")
    state = (await visibility.inner_text()).strip()
    await dom_click(visibility)

    try:
        await page.get_by_text("Save or publish", exact=True).wait_for(
            state="visible", timeout=5000)
    except Exception as exc:
        raise RuntimeError("Save or publish panel did not open") from exc
    return state


async def open_schedule(page):
    schedule = await first_visible((
        page.locator("ytcp-accordion").filter(has_text="Schedule"),
        page.locator("ytcp-expansion-panel").filter(has_text="Schedule"),
        page.get_by_text("Schedule", exact=True),
    ))
    if schedule is None:
        raise RuntimeError("Schedule section not found")
    await schedule.evaluate("""el => {
      const target = el.closest('ytcp-accordion, ytcp-expansion-panel, button, [role=button]') || el;
      target.click();
    }""")
    try:
        await page.get_by_text("Schedule as public", exact=False).wait_for(
            state="visible", timeout=5000)
    except Exception as exc:
        raise RuntimeError("Schedule section did not expand") from exc


async def choose_date(page, date_text):
    trigger = await first_visible((
        page.locator("#datepicker-trigger"),
        page.locator("ytcp-text-dropdown-trigger").filter(has_text=","),
    ))
    if trigger is None:
        raise RuntimeError("date picker was not found")
    if date_text.lower() in (await trigger.inner_text()).lower():
        return

    await dom_click(trigger)
    await page.wait_for_timeout(350)

    choice = await first_visible((
        page.locator(f'[aria-label="{date_text}"]'),
        page.get_by_role("button", name=date_text, exact=True),
        page.get_by_text(date_text, exact=True),
    ))
    if choice is not None:
        await dom_click(choice)
    else:
        # The 2026 picker exposes a text input containing the currently selected
        # date instead of labelling each day button with a full date.
        popup_input = None
        inputs = page.locator("input")
        for index in range(await inputs.count()):
            candidate = inputs.nth(index)
            if not await candidate.is_visible():
                continue
            value = await candidate.input_value()
            if re.search(r"[A-Za-z]{3} \d{1,2}, \d{4}", value):
                popup_input = candidate
        if popup_input is None:
            fields = await visible_field_dump(page.locator("body"))
            raise RuntimeError(
                f"date choice {date_text!r} not found; visible fields={fields}")
        await popup_input.fill(date_text)
        await popup_input.press("Enter")

    await page.wait_for_timeout(400)
    actual = (await trigger.inner_text()).strip()
    if date_text.lower() not in actual.lower():
        raise RuntimeError(
            f"date was not accepted: expected {date_text!r}, got {actual!r}")


async def fill_time(page, time_text):
    time_input = None
    inputs = page.locator("input")
    for index in range(await inputs.count()):
        candidate = inputs.nth(index)
        if not await candidate.is_visible():
            continue
        value = await candidate.input_value()
        if ":" in value:
            time_input = candidate
            break
    if time_input is None:
        fields = await visible_field_dump(page.locator("body"))
        raise RuntimeError(f"time input not found; visible fields={fields}")

    await time_input.fill(time_text)
    await time_input.press("Tab")
    await page.wait_for_timeout(350)
    actual = re.sub(r"\s+", " ", await time_input.input_value()).strip()
    if time_text.lower() != actual.lower():
        raise RuntimeError(
            f"time was not accepted: expected {time_text!r}, got {actual!r}")


async def schedule_values(page):
    trigger = await first_visible((
        page.locator("#datepicker-trigger"),
        page.locator("ytcp-text-dropdown-trigger").filter(has_text=","),
    ))
    if trigger is None:
        raise RuntimeError("date picker was not found")
    time_input = None
    inputs = page.locator("input")
    for index in range(await inputs.count()):
        candidate = inputs.nth(index)
        if await candidate.is_visible() and ":" in await candidate.input_value():
            time_input = candidate
            break
    if time_input is None:
        raise RuntimeError("time input was not found")
    date_value = (await trigger.inner_text()).strip()
    time_value = re.sub(r"\s+", " ", await time_input.input_value()).strip()
    return date_value, time_value


async def assert_timezone(page, expected):
    aliases = {part.strip().lower() for part in expected.split("|") if part.strip()}
    button = await first_visible((
        page.get_by_role("button", name="Time zone", exact=True),
        page.locator('button[aria-label="Time zone"]'),
    ))
    if button is None:
        raise RuntimeError("Time zone control not found")
    await dom_click(button)
    await page.wait_for_timeout(300)
    text = (await page.locator("body").inner_text()).lower()
    await page.keyboard.press("Escape")
    if aliases and not any(alias in text for alias in aliases):
        raise RuntimeError(f"schedule timezone is not {expected!r}")


async def schedule_one(page, args):
    date_text = display_date(args.date)
    time_text = display_time(args.time)

    await page.goto(f"{STUDIO}/video/{args.video_id}/edit",
                    wait_until="domcontentloaded", timeout=60_000)
    if await wait_for_edit_surface(page) is None:
        raise RuntimeError("video edit surface did not mount")
    await ui.dismiss_overlays(page)
    if f"/video/{args.video_id}/edit" not in page.url:
        raise RuntimeError(f"edit page did not open for {args.video_id}")
    body_text = await page.locator("body").inner_text()
    if args.title and args.title.lower() not in body_text.lower():
        raise RuntimeError(f"title check failed for video {args.video_id}")
    await shot(page, "schedule_01_edit", args.debug)
    prior_state = await open_visibility_editor(page)
    await shot(page, "schedule_02_visibility", args.debug)
    if args.publish_now:
        public = await first_visible((
            page.locator("tp-yt-paper-radio-button[name='PUBLIC']"),
            page.get_by_text("Public", exact=True),
        ))
        if public is None:
            raise RuntimeError("Public visibility option was not found")
        await dom_click(public)
        await page.wait_for_timeout(400)
        if (await public.get_attribute("aria-checked")) not in ("true", None):
            raise RuntimeError("Public visibility was not selected")
        done = await first_visible((
            page.get_by_role("button", name="Done", exact=True),
            page.locator("ytcp-button").filter(has_text=re.compile(r"^Done$")),
        ))
        if done is None or await done.is_disabled():
            raise RuntimeError("Done button is not enabled")
        await dom_click(done)
        await page.wait_for_timeout(700)
        save = await first_visible((
            page.get_by_role("button", name="Save", exact=True),
            page.locator("ytcp-button").filter(has_text=re.compile(r"^Save$")),
        ))
        if save is None or await save.is_disabled():
            raise RuntimeError("top Save button is not enabled")
        await dom_click(save)
        if not await wait_for_save_landed(page, save):
            raise RuntimeError("Studio did not finish saving Public visibility")
        if not await wait_for_public_visibility(page):
            raise RuntimeError("Studio did not retain Public visibility")
        await shot(page, "schedule_03_published", args.debug)
        log(f"  PUBLISHED {args.video_id}")
        return
    await open_schedule(page)
    current_date, current_time = await schedule_values(page)
    if ("scheduled" in prior_state.lower()
            and current_date.lower() == date_text.lower()
            and current_time.lower() == time_text.lower()):
        log(f"  already scheduled {args.video_id}: {date_text} {time_text}")
        return
    await choose_date(page, date_text)
    await fill_time(page, time_text)
    await assert_timezone(page, args.expect_timezone)
    await shot(page, "schedule_03_filled", args.debug)

    if args.dry_run:
        log("  DRY RUN: schedule is filled but not saved")
        return

    done = await first_visible((
        page.get_by_role("button", name="Done", exact=True),
        page.locator("ytcp-button").filter(has_text=re.compile(r"^Done$")),
    ))
    if done is None or await done.is_disabled():
        raise RuntimeError("Done button is not enabled")
    await dom_click(done)
    await page.wait_for_timeout(700)

    save = await first_visible((
        page.get_by_role("button", name="Save", exact=True),
        page.locator("ytcp-button").filter(has_text=re.compile(r"^Save$")),
    ))
    if save is None or await save.is_disabled():
        raise RuntimeError("top Save button is not enabled")
    await dom_click(save)
    await page.wait_for_timeout(1800)

    await open_visibility_editor(page)
    await open_schedule(page)
    actual_date, actual_time = await schedule_values(page)
    if (actual_date.lower() != date_text.lower()
            or actual_time.lower() != time_text.lower()):
        raise RuntimeError(
            "Studio saved a different schedule: "
            f"{actual_date} {actual_time}")
    log(f"  SCHEDULED {args.video_id}: {date_text} {time_text}")


async def run(args):
    async with make_camoufox(False) as context:
        page = await prepare_page(context)
        await page.goto(STUDIO, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2500)
        if not await logged_in_youtube(page):
            raise RuntimeError("not logged into YouTube")

        wanted = await resolve_channel_id(page, args.channel_handle)
        if not wanted:
            raise RuntimeError(f"could not resolve channel {args.channel_handle}")
        active = await select_channel(page, channel_id=wanted,
                                      handle=args.channel_handle)
        if active != wanted:
            raise RuntimeError(f"wrong active channel: wanted {wanted}, got {active}")
        await schedule_one(page, args)


def parse_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # YouTube ids may begin with "-". Join such a value to its option so
    # argparse does not mistake the id for another flag.
    for index in range(len(argv) - 1):
        if argv[index] == "--video-id" and argv[index + 1].startswith("-"):
            argv[index:index + 2] = [f"--video-id={argv[index + 1]}"]
            break
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel-handle", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--title", default="", help="optional title assertion")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD in Studio timezone")
    parser.add_argument("--time", required=True, help="HH:MM or H:MM AM/PM")
    parser.add_argument("--expect-timezone", default="Pacific|GMT-7|PDT|PT")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish-now", action="store_true",
                        help="switch an existing private video to public")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        asyncio.run(run(args))
    except (RuntimeError, ValueError) as exc:
        log(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
