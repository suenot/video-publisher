import re
from camoufox_session import log

STUDIO = "https://studio.youtube.com"


def normalize_handle(handle):
    h = handle.strip().rstrip("/")
    h = h.split("/")[-1]
    if not h.startswith("@"):
        h = "@" + h
    return h


def channel_id_from_url(url):
    m = re.search(r"/channel/(UC[\w-]+)", url or "")
    return m.group(1) if m else None


async def _click_switch_card(page, needle):
    """Click the account-switcher card whose text contains `needle` (a handle or
    a channel name). Cards are ytd/yt-formatted rows, not plain buttons, so match
    on any clickable ancestor holding the text."""
    js = """
    (needle) => {
      needle = needle.toLowerCase();
      const nodes = Array.from(document.querySelectorAll(
        "ytd-account-item-renderer, yt-formatted-string, tp-yt-paper-item, a, div, span"));
      for (const n of nodes) {
        const t = (n.innerText || n.textContent || '').toLowerCase();
        if (t.includes(needle)) {
          let el = n;
          for (let i = 0; i < 6 && el; i++) {
            if (el.tagName && /A|YTD-ACCOUNT-ITEM-RENDERER|TP-YT-PAPER-ITEM|BUTTON/.test(el.tagName)) {
              el.scrollIntoView(); el.click(); return true;
            }
            el = el.parentElement;
          }
          n.scrollIntoView(); n.click(); return true;
        }
      }
      return false;
    }
    """
    try:
        return await page.evaluate(js, needle)
    except Exception:
        return False


async def select_channel(page, channel_id=None, handle=None):
    """Switch Studio's active channel to a brand channel via the account switcher.
    Deep-linking to /channel/<id> does NOT work for brand channels (permission
    error) — you must switch account context. Match the card by handle."""
    if not handle and not channel_id:
        return channel_id_from_url(page.url)
    await page.goto(STUDIO, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3000)
    # Open the account menu (avatar), then "Switch account".
    for sel in ("button#avatar-btn", "ytcp-icon-button#avatar-btn",
                "button[aria-label='Account']"):
        b = page.locator(sel)
        try:
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click(timeout=4000)
                break
        except Exception:
            continue
    await page.wait_for_timeout(1500)
    # click_text lives in youtube_ui; import locally to avoid a cycle at module load.
    import youtube_ui as ui
    await ui.click_text(page, ["Switch account"], 5000)
    await page.wait_for_timeout(2500)
    needle = normalize_handle(handle) if handle else channel_id
    ok = await _click_switch_card(page, needle)
    if not ok and handle:
        # fall back to matching without the leading '@'
        ok = await _click_switch_card(page, normalize_handle(handle).lstrip("@"))
    await page.wait_for_timeout(4000)
    active = channel_id_from_url(page.url)
    if channel_id and active and active != channel_id:
        log(f"  WARNING: asked for {channel_id} but active channel is {active}")
    else:
        log(f"  switched; active channel: {active} (matched '{needle}', clicked={ok})")
    return active
