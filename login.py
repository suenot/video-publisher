import argparse
import asyncio
import sys
from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log


async def run(headless):
    async with make_camoufox(headless) as ctx:
        page = await prepare_page(ctx)
        await page.goto("https://studio.youtube.com",
                        wait_until="domcontentloaded", timeout=60_000)
        log("Sign into the TARGET YouTube account in this window.")
        for _ in range(3600):  # up to ~1h
            if await logged_in_youtube(page):
                log("Logged in — session saved to .camoufox_profile/. You can close now.")
                await page.wait_for_timeout(2000)
                return 0
            await page.wait_for_timeout(1000)
        log("Timed out waiting for sign-in.")
        return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run(a.headless))


if __name__ == "__main__":
    sys.exit(main())
