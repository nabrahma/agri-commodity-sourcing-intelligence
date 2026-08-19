"""Capture dashboard screenshots for the README.

Runs the app in a headless browser, clicks through every tab and saves a
full-page image of each.

Playwright is deliberately not in requirements.txt: it pulls a ~115 MB
browser that CI has no use for. Install it only when regenerating images:

    pip install playwright && playwright install chromium
    make dashboard &            # or: streamlit run dashboard/app.py
    make screenshots
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "docs" / "screenshots"
URL = "http://localhost:8501"

VIEWPORT = {"width": 1500, "height": 1000}

# Tab label as rendered, and the filename it is saved under.
TABS = [
    ("Spread", "01-spread"),
    ("Seasonality", "02-seasonality"),
    ("Markets", "03-markets"),
    ("Simulation", "04-simulation"),
    ("Sensitivity", "05-sensitivity"),
]

RENDER_WAIT_SECONDS = 4.0


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        time.sleep(RENDER_WAIT_SECONDS)

        for label, filename in TABS:
            try:
                page.get_by_role("tab", name=label).click()
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                print(f"  {label}: could not select tab ({type(exc).__name__})")
                continue

            # Streamlit renders charts after the tab switch; give plotly time
            # to draw or the image captures an empty container.
            time.sleep(RENDER_WAIT_SECONDS)
            page.mouse.wheel(0, 400)
            time.sleep(1.0)
            page.mouse.wheel(0, -400)
            time.sleep(0.5)

            path = OUT_DIR / f"{filename}.png"
            page.screenshot(path=str(path), full_page=True)
            size_kb = path.stat().st_size / 1024
            print(f"  {label:14s} -> {path.name} ({size_kb:,.0f} KB)")

        browser.close()

    print(f"\nwrote {len(list(OUT_DIR.glob('*.png')))} screenshots to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
