"""Wake a Streamlit Community Cloud app with a real browser session.

Plain HTTP pings only hit the static shell; the Python process wakes when
Chromium loads the page, runs JS, and (if needed) clicks the wake button.
"""

from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get(
    "STREAMLIT_APP_URL",
    "https://virtual-mockup-fe3z8xxueqz7xjjb8wvcnt.streamlit.app/",
).rstrip("/") + "/"
HOLD_SECONDS = int(os.environ.get("KEEPALIVE_HOLD_SECONDS", "45"))


def main() -> int:
    print(f"Opening {APP_URL}")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=180_000)
        time.sleep(5)

        for label in (
            "Yes, get this app back up!",
            "Yes, get this app back up",
            "Get this app back up",
        ):
            button = page.get_by_role("button", name=label)
            if button.count():
                print(f"Clicking wake button: {label}")
                button.first.click()
                page.wait_for_load_state("domcontentloaded", timeout=180_000)
                break

        print(f"Holding session open for {HOLD_SECONDS}s")
        time.sleep(HOLD_SECONDS)
        title = page.title()
        print(f"Done. page title={title!r}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
