#!/usr/bin/env python3
"""Edit an already-published YouTube video's metadata (title/description/tags)
via YouTube Studio, through Camoufox on the publisher profile.

Reuses publish.py's session/ui helpers. Complements publish.py (upload-only).

Usage:
  venv/bin/python edit_video.py --video-id VIDEO_ID \
      --metadata path/to/_metadata.json [--channel-handle @suenot] \
      [--keep-open] [--debug]

The metadata JSON supplies title/description/tags (same shape publish.py uses).
"""
import argparse
import asyncio
import sys
from pathlib import Path

from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log, shot
from channel import _strip_backdrops
import youtube_ui as ui
from metadata import load_metadata

STUDIO = "https://studio.youtube.com"


async def _goto(page, url, tries=3):
    last = None
    for _ in range(tries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            return
        except Exception as e:
            last = e
            await page.wait_for_timeout(1500)
    if last:
        raise last


async def _wait_login(page, timeout_s=120):
    """If YouTube redirects to a login/verify gate, wait for a human to pass it."""
    for _ in range(timeout_s // 5):
        if await logged_in_youtube(page):
            return True
        await page.wait_for_timeout(5000)
    return await logged_in_youtube(page)


async def set_tags(page, tags, debug):
    """Replace the tags in the edit page's Tags box.

    On the post-publish edit page the Tags box is hidden behind a SHOW MORE
    expansion (unlike the upload dialog where it is inline). Expand first, then
    the chip input appears as <input aria-label='Tags'>. Clear existing chips
    via backspace, then type each tag + Enter.
    """
    # Expand the collapsed section that contains Tags.
    for label in ("SHOW MORE", "Show more", "show more", "Показать больше"):
        try:
            await ui.click_text(page, [label], 4000)
            log(f"  expanded '{label}'")
            break
        except Exception:
            continue
    await page.wait_for_timeout(2500)

    box = await ui.first_present(
        page,
        ["input[aria-label='Tags']", "input[aria-label*='Tags' i]",
         "#tags-container input", "#tags-input input",
         "ytcp-social-suggestions-textbox#tags-input input"],
        15000)
    if box is None:
        log("  tags box not found; skipping tags")
        return False
    try:
        await box.click()
        # Clear existing chips: backspace deletes the last chip each press.
        for _ in range(60):
            await page.keyboard.press("Backspace")
        for t in tags:
            await box.type(t, delay=20)
            await page.wait_for_timeout(150)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(150)
    except Exception as e:
        log(f"  tags set failed: {e}")
        return False
    log(f"  tags set ({len(tags)})")
    await shot(page, "edit_tags", debug)
    return True


async def save(page, debug):
    """Click the Save button (top-right). Returns True if clicked."""
    # Studio's current edit page exposes a plain button with aria-label=Save;
    # older layouts used #save-button or ytcp-button#save.
    btn = await ui.first_present(
        page,
        ["button[aria-label='Save']", "ytcp-button[aria-label='Save']",
         "ytcp-button#save", "#save-button", "#submit-button",
         "button:has-text('Save')", "button:has-text('SAVE')"],
        15000)
    if btn is None:
        log("  no Save button (already saved?)")
        return False
    try:
        await ui.mouse_click(page, btn)
        log("  clicked Save")
    except Exception as e:
        # mouse_click fallback to plain click
        try:
            await btn.click()
            log("  clicked Save (plain)")
        except Exception as e2:
            log(f"  Save click failed: {e2}")
            return False
    await page.wait_for_timeout(4000)
    await shot(page, "edit_saved", debug)
    return True


async def edit_one(video_id, meta, channel_handle, keep_open, debug):
    async with make_camoufox(headless=False) as ctx:
        page = await prepare_page(ctx)
        url = f"{STUDIO}/video/{video_id}/edit"
        await _goto(page, url)
        await page.wait_for_timeout(3500)
        await ui.dismiss_overlays(page)
        await _strip_backdrops(page)

        if not await logged_in_youtube(page):
            log("  not logged in / verify gate — waiting up to 5 min for human")
            await shot(page, "edit_gate", debug)
            ok = await _wait_login(page, timeout_s=300)
            if not ok:
                log("  ERROR: still not logged in after wait")
                return False
            await _goto(page, url)
            await page.wait_for_timeout(3500)

        await shot(page, "edit_01_loaded", debug)

        # Title
        tb = await ui.first_present(page, ["#title-textarea #textbox",
                                           "#title-wrapper #textbox"], 30000)
        if tb is not None and meta.get("title"):
            await ui.fill_contenteditable(page, tb, meta["title"])
            log("  title updated")
        else:
            log("  WARN: title box not found")

        # Description
        db = await ui.first_present(page, ["#description-textarea #textbox",
                                           "#description-wrapper #textbox"], 10000)
        if db is not None and meta.get("description"):
            await ui.fill_contenteditable(page, db, meta["description"])
            log("  description updated")
        else:
            log("  WARN: description box not found")

        await set_tags(page, meta.get("tags", []), debug)

        await page.wait_for_timeout(1000)
        ok = await save(page, debug)
        if not ok:
            log("  ERROR: could not Save")
            return False

        log(f"  EDIT COMPLETE for {video_id}")
        if keep_open:
            log("  --keep-open: browser stays open. Ctrl+C to quit.")
            try:
                while True:
                    await page.wait_for_timeout(60000)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
        return True


def main(argv=None):
    p = argparse.ArgumentParser(description="Edit a published YouTube video's metadata via Camoufox.")
    p.add_argument("--video-id", required=True)
    p.add_argument("--metadata", required=True, help="metadata JSON (title/description/tags)")
    p.add_argument("--channel-handle", default="")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args(argv)

    meta = load_metadata(args.metadata, "", "", "")
    ok = asyncio.run(edit_one(args.video_id, meta, args.channel_handle,
                              args.keep_open, args.debug))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
