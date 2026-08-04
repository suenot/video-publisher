#!/usr/bin/env python3
"""Upload a timed SRT caption track to an existing YouTube Studio video.

This is deliberately a separate publishing step: subtitles embedded in a
render or created by Whisper are not discoverable as a YouTube caption track
until they are uploaded in Studio.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log, shot
from channel import resolve_channel_id, select_channel
import youtube_ui as ui

STUDIO = "https://studio.youtube.com"


async def deep_click_text(page, phrases, timeout_ms=8000):
    """Click a visible Studio control by text, including open shadow roots."""
    wanted = [phrase.lower() for phrase in phrases]
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    script = r"""wanted => {
      const seen = new Set();
      function walk(root) {
        const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (const el of all) {
          if (seen.has(el)) continue; seen.add(el);
          const rect = el.getBoundingClientRect();
          if (!rect.width || !rect.height) { if (el.shadowRoot) walk(el.shadowRoot); continue; }
          const text = ((el.getAttribute('aria-label') || '') + ' ' +
            (el.innerText || el.textContent || '')).replace(/\s+/g, ' ').trim().toLowerCase();
          const clickable = el.matches('button, [role=button], [role=menuitem], [role=radio], tp-yt-paper-item, ytcp-button, a') ||
            el.closest('button, [role=button], [role=menuitem], [role=radio], tp-yt-paper-item, ytcp-button, a');
          if (clickable && wanted.some(word => text.includes(word))) {
            (el.closest('button, [role=button], [role=menuitem], [role=radio], tp-yt-paper-item, ytcp-button, a') || el).click();
            return true;
          }
          if (el.shadowRoot) { const hit = walk(el.shadowRoot); if (hit) return true; }
        }
        return false;
      }
      return walk(document);
    }"""
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await page.evaluate(script, wanted):
                await page.wait_for_timeout(500)
                return True
        except Exception:
            pass
        await page.wait_for_timeout(350)
    return False


async def file_input(page, timeout_ms=8000):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        handles = await page.query_selector_all("input[type='file']")
        if handles:
            return handles[-1]
        await page.wait_for_timeout(300)
    return None


async def upload_one(page, args):
    await page.goto(f"{STUDIO}/video/{args.video_id}/subtitles",
                    wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(6000)
    await ui.dismiss_overlays(page)
    if f"/video/{args.video_id}" not in page.url:
        raise RuntimeError("subtitle page did not open")
    text = await ui.all_text(page)
    if args.title and args.title.lower() not in text:
        raise RuntimeError("title check failed on subtitle page")

    # Add the requested language only when the language row is absent.
    if args.language.lower() not in text:
        if not await deep_click_text(page, ["add language"]):
            raise RuntimeError("Add language control not found")
        await page.wait_for_timeout(500)
        field = await page.query_selector("input[placeholder], input")
        if field is None:
            raise RuntimeError("language search field not found")
        await field.fill(args.language)
        await page.wait_for_timeout(600)
        if not await deep_click_text(page, [args.language]):
            raise RuntimeError(f"language {args.language!r} not selectable")
        await page.wait_for_timeout(1200)

    # The subtitles row shows Add under the Subtitles column. Existing tracks
    # open the editor instead; this avoids silently creating a duplicate.
    text = await ui.all_text(page)
    if "published" in text and args.language.lower() in text:
        raise RuntimeError("a published caption track already exists; refusing to overwrite it")
    if not await deep_click_text(page, ["add"]):
        raise RuntimeError("Subtitles Add control not found")
    await page.wait_for_timeout(700)
    if not await deep_click_text(page, ["upload file"]):
        raise RuntimeError("Upload file action not found")
    await page.wait_for_timeout(600)
    if not await deep_click_text(page, ["with timing"]):
        raise RuntimeError("With timing option not found")
    handle = await file_input(page)
    if handle is None:
        raise RuntimeError("caption file input not found")
    await handle.set_input_files(str(args.srt))
    await page.wait_for_timeout(2500)
    await shot(page, "captions_01_uploaded", args.debug)
    if not await deep_click_text(page, ["publish"]):
        raise RuntimeError("caption Publish control not found")
    await page.wait_for_timeout(1800)
    final_text = await ui.all_text(page)
    if "published" not in final_text:
        raise RuntimeError("Studio did not confirm the caption track as published")
    log(f"CAPTIONS_PUBLISHED {args.video_id}: {args.srt.name}")


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
        active = await select_channel(page, channel_id=wanted, handle=args.channel_handle)
        if active != wanted:
            raise RuntimeError(f"wrong active channel: wanted {wanted}, got {active}")
        await upload_one(page, args)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel-handle", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--language", default="English")
    parser.add_argument("--title", default="")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if not args.srt.is_file():
        parser.error(f"caption file does not exist: {args.srt}")
    if args.srt.suffix.lower() != ".srt":
        parser.error("only .srt tracks are supported")
    return args


def main(argv=None):
    try:
        asyncio.run(run(parse_args(argv)))
    except RuntimeError as exc:
        log(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
