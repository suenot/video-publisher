#!/usr/bin/env python3
"""Delete individual tag chips from a published video.

edit_details.py clears the tags field by pressing Backspace sixty times, which
silently does nothing when the caret is not in the chip input -- a fused chip
("terminal tooai agents explained", two tags typed too fast into an
autocompleting field) then survives every re-run. Clicking a chip's own X is
unambiguous, so remove the bad ones by exact label instead.

    python remove_tag.py @suenot VIDEO_ID "bad tag text" ["another bad tag"]
"""
import asyncio
import sys
from pathlib import Path

from camoufox_session import make_camoufox, prepare_page, log
from channel import select_channel

STUDIO_VIDEO = "https://studio.youtube.com/video/{vid}/edit"


async def expand_advanced(page) -> bool:
    tog = page.locator("ytcp-button#toggle-button")
    if await tog.count() == 0:
        return False
    for i in range(await tog.count()):
        b = tog.nth(i)
        try:
            label = (await b.inner_text()).strip().lower()
        except Exception:
            continue
        if "less" in label:
            return True
        if "more" in label:
            try:
                await b.scroll_into_view_if_needed(timeout=5000)
                await b.click(timeout=5000, force=True)
                await page.wait_for_timeout(2500)
                if "less" in (await b.inner_text()).strip().lower():
                    return True
            except Exception:
                continue
    return False


async def remove(page, vid: str, bad: list[str]) -> bool:
    await page.goto(STUDIO_VIDEO.format(vid=vid), wait_until="domcontentloaded",
                    timeout=60_000)
    await page.wait_for_timeout(7000)
    if not await expand_advanced(page):
        log("  could not open advanced settings")
        return False
    await page.wait_for_timeout(1000)

    removed = 0
    for text in bad:
        chip = page.locator("ytcp-chip").filter(has_text=text)
        if await chip.count() == 0:
            log(f"  chip not found: {text!r}")
            continue
        target = chip.first
        for sel in ("#delete-icon", "ytcp-icon-button", "[aria-label*='Remove']", "svg"):
            try:
                await target.locator(sel).first.click(timeout=4000, force=True)
                await page.wait_for_timeout(800)
                break
            except Exception:
                continue
        if await page.locator("ytcp-chip").filter(has_text=text).count() == 0:
            log(f"  removed: {text!r}")
            removed += 1
        else:
            log(f"  still present: {text!r}")

    if not removed:
        return False

    await page.screenshot(path=f"debug/tags_{vid}_after_remove.png")
    for name in ("Save", "SAVE"):
        try:
            await page.get_by_role("button", name=name).first.click(timeout=6000)
            await page.wait_for_timeout(5000)
            log(f"{vid} SAVED")
            return True
        except Exception:
            continue
    log("  could not click Save")
    return False


async def main(handle: str, vid: str, bad: list[str]) -> int:
    async with make_camoufox(False) as ctx:
        page = await prepare_page(ctx)
        await select_channel(page, handle=handle)
        ok = await remove(page, vid, bad)
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3:])))
