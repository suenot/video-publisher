"""Set video language via the Languages tab dialog.

The Studio language dropdown is scroll-virtualized: an option's element only
exists in the DOM while scrolled near. Open the dropdown, scroll the list
container until the wanted option mounts, dispatch a real click sequence on it,
then press Confirm.
"""
import argparse
import asyncio

from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log
from channel import resolve_channel_id, select_channel
import youtube_ui as ui

STUDIO = "https://studio.youtube.com"

CLICK_TEXT_JS = r"""needle => {
  const seen = new Set(), items = [];
  function walk(root) {
    for (const el of root && root.querySelectorAll ? root.querySelectorAll('*') : []) {
      if (seen.has(el)) continue; seen.add(el);
      const box = el.getBoundingClientRect();
      const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      if (box.width && box.height && text.toLowerCase() === needle) items.push({el, area: box.width * box.height});
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  }
  walk(document);
  if (!items.length) return false;
  items.sort((a, b) => a.area - b.area);
  const el = items[0].el;
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, composed: true}));
  }
  return true;
}"""

SCROLL_FIND_CLICK_JS = r"""needle => {
  const seen = new Set(), lists = [];
  function collect(root) {
    for (const el of root && root.querySelectorAll ? root.querySelectorAll('*') : []) {
      if (seen.has(el)) continue; seen.add(el);
      if (el.scrollHeight > el.clientHeight + 40 && el.clientHeight > 200) lists.push(el);
      if (el.shadowRoot) collect(el.shadowRoot);
    }
  }
  collect(document);
  const want = needle.toLowerCase();
  function findOption() {
    const s = new Set(), hits = [];
    function walk(root) {
      for (const el of root && root.querySelectorAll ? root.querySelectorAll('*') : []) {
        if (s.has(el)) continue; s.add(el);
        const box = el.getBoundingClientRect();
        const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
        if (box.width && box.height && text.toLowerCase() === want) hits.push({el, area: box.width * box.height});
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    }
    walk(document);
    hits.sort((a, b) => a.area - b.area);
    return hits.length ? hits[0].el : null;
  }
  let opt = findOption();
  if (!opt) {
    for (const list of lists.slice(0, 5)) {
      for (let i = 0; i < 40 && !opt; i++) {
        list.scrollTop = list.scrollHeight;
        opt = findOption();
        if (opt) break;
        list.scrollTop = Math.max(0, list.scrollTop - 400);
        opt = findOption();
      }
      if (opt) break;
    }
  }
  if (!opt) return {ok: false, reason: 'option never mounted', lists: lists.length};
  opt.scrollIntoView({block: 'center'});
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    opt.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, composed: true}));
  }
  return {ok: true};
}"""


async def run(args):
    async with make_camoufox(False) as context:
        page = await prepare_page(context)
        await page.goto(STUDIO, wait_until="commit", timeout=30_000)
        await page.wait_for_timeout(2500)
        if not await logged_in_youtube(page):
            raise RuntimeError("not logged into YouTube")
        wanted = await resolve_channel_id(page, args.channel_handle)
        await select_channel(page, channel_id=wanted, handle=args.channel_handle)

        await page.goto(f"{STUDIO}/video/{args.video_id}/translations",
                        wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(8000)
        await ui.dismiss_overlays(page)

        if not await page.evaluate(CLICK_TEXT_JS, "set language"):
            raise RuntimeError("Set language control not found")
        await page.wait_for_timeout(1500)

        result = await page.evaluate(SCROLL_FIND_CLICK_JS, args.language)
        log(f"  option pick: {result}")
        if not result.get("ok"):
            raise RuntimeError(f"option {args.language!r} not reachable")
        await page.wait_for_timeout(1200)
        if not await page.evaluate(CLICK_TEXT_JS, "confirm"):
            raise RuntimeError("Confirm control not found")
        await page.wait_for_timeout(3000)

        text = (await ui.all_text(page)).lower()
        ok = f"{args.language.lower()} (video language)" in text
        log(f"RESULT: {'OK' if ok else 'NOT_CONFIRMED'}")
        await page.screenshot(path="debug/set_language_result.png")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--channel-handle", required=True)
    p.add_argument("--video-id", required=True)
    p.add_argument("--language", default="English")
    return p.parse_args()


asyncio.run(run(parse_args()))
