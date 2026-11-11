"""
Cricbuzz live score with Playwright.

The score isn't in the HTML the server sends first; JavaScript fills it in
after the page loads. Playwright drives a real browser, so it waits for that
JavaScript to run and then reads the page exactly as you'd see it.

Setup (once):
    pip install playwright
    python -m playwright install chromium

Run:
    python cricbuzz_score.py                 # picks the current live match
    python cricbuzz_score.py <match-url>     # or score a specific match
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE = "https://www.cricbuzz.com"
LIVE_SCORES = f"{BASE}/cricket-match/live-scores"
MATCH_LINK = "a[href*='/live-cricket-scores/']"

# A score looks like "311/4" or "434". We wait until one of these is on the page.
SCORE_PATTERN = re.compile(r"\d{1,3}\s*/\s*\d{1,2}|\d{1,3}\s*\(\d")

# The score block: a column holding the innings rows (div.gap-0) and, after
# them, a status line ("Sri Lanka trail by 123 runs", "India won by 5 wkts").
SCORE_BLOCK = "div.flex-col:has(> div.gap-0)"


def find_match_url(page) -> str:
    """Open the live-scores list and return the URL of a match worth scoring."""
    page.goto(LIVE_SCORES, wait_until="domcontentloaded")
    page.wait_for_selector(MATCH_LINK, timeout=30_000)

    # Prefer a match carrying the red "LIVE" badge; otherwise take the first one.
    live = page.locator(MATCH_LINK, has_text="LIVE")
    link = live.first if live.count() else page.locator(MATCH_LINK).first
    return BASE + link.get_attribute("href")


def read_score(page) -> dict:
    """Wait for the JavaScript-rendered score to appear, then read it."""
    block = page.locator(SCORE_BLOCK).filter(has_text=SCORE_PATTERN).first
    block.wait_for(state="visible", timeout=30_000)

    # Each innings row, e.g. "PAK 434/9 d" or "SL 311/4 (81) CRR: 3.84".
    rows = [
        " ".join(row.inner_text().split()).replace(" /", "/")
        for row in block.locator("div.gap-0 > div").all()
    ]
    status = " ".join(block.locator("> div").last.inner_text().split())

    return {
        "match": page.locator("h1").first.inner_text().strip(),
        "innings": rows,
        "status": status,
    }


def main() -> None:
    out_dir = Path(__file__).parent
    with sync_playwright() as p:
        # Cricbuzz returns "Access Denied" to headless browsers, so open a
        # real (visible) window. channel="msedge" uses the Edge that ships
        # with Windows; drop it to use Playwright's bundled Chromium.
        browser = p.chromium.launch(channel="msedge", headless=False)
        page = browser.new_page(viewport={"width": 1366, "height": 900})

        try:
            url = sys.argv[1] if len(sys.argv) > 1 else find_match_url(page)
            page.goto(url, wait_until="domcontentloaded")
            if "Access Denied" in page.title():
                sys.exit("Cricbuzz blocked this browser (Access Denied).")

            try:
                score = read_score(page)
            except PlaywrightTimeout:
                # Layout changed or no score yet: the tab title still carries it.
                score = {"match": page.title(), "innings": [], "status": ""}

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot = out_dir / f"cricbuzz_{stamp}.png"
            page.screenshot(path=str(shot))
        except PlaywrightError as err:
            if "closed" in str(err):
                sys.exit("The browser window was closed before the score loaded. "
                         "Leave it open until the script finishes.")
            raise
        finally:
            browser.close()

    print(f"\n{score['match']}")
    print("-" * len(score["match"]))
    for row in score["innings"]:
        print(f"  {row}")
    if score["status"]:
        print(f"\n  {score['status']}")
    print(f"\nSource:     {url}")
    print(f"Screenshot: {shot}")


if __name__ == "__main__":
    main()
