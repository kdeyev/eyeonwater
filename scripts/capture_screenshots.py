"""Playwright script to capture HA screenshots for EyeOnWater documentation.

Captures anonymized screenshots by injecting CSS/JS to hide/replace
sensitive information (meter IDs, usernames, utility names) before
taking each screenshot.

Usage:
    python scripts/capture_screenshots.py [--base-url URL]

The script opens a headed Chrome browser. If you need to log in,
do so manually — the script waits for you at each step.
"""

import argparse
import asyncio
import contextlib
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE_URL = "https://i3tsw95ldu5cyffzqgkuudu1k8uvwxyv.ui.nabu.casa"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "img"


async def wait_for_ha_loaded(page: Page, timeout: int = 60_000) -> None:
    """Wait until HA frontend finishes loading (spinner gone)."""
    await page.wait_for_load_state("networkidle", timeout=timeout)
    await page.wait_for_timeout(2000)


# ── Anonymization ─────────────────────────────────────────────────────

# Patterns to find and replace in all text nodes across all shadow DOMs.
# Order matters — more specific patterns first.
TEXT_REPLACEMENTS = [
    ("452170", "XXXXX"),
    ("CINCO MUD #14", "Example Utility"),
    ("CINCO MUD # 14", "Example Utility"),
    ("CINCO MUD", "Example Utility"),
    ("2.10.620", "X.XX.XXX"),
    ("68781-001.5", "XXXXX-XXX.X"),
    ("952,685", "XXX,XXX"),
    ("952.685", "XXX,XXX"),
    ("kostya", "user"),
    ("Kostya", "User"),
]

ANONYMIZE_JS = """
(replacements) => {
    function replaceInText(text) {
        for (const [from, to] of replacements) {
            text = text.split(from).join(to);
        }
        return text;
    }

    function processRoot(root) {
        // Replace text nodes
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        for (const node of nodes) {
            const orig = node.textContent;
            const replaced = replaceInText(orig);
            if (replaced !== orig) node.textContent = replaced;
        }

        // Replace title and aria-label attributes
        for (const el of root.querySelectorAll('[title], [aria-label]')) {
            if (el.title) el.title = replaceInText(el.title);
            if (el.ariaLabel) el.ariaLabel = replaceInText(el.ariaLabel);
        }

        // Replace value in input fields
        for (const el of root.querySelectorAll('input, textarea')) {
            if (el.value) {
                const replaced = replaceInText(el.value);
                if (replaced !== el.value) el.value = replaced;
            }
        }

        // Recurse into shadow roots
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) processRoot(el.shadowRoot);
        }
    }

    processRoot(document);

    // Also hide the user profile badge at the bottom of sidebar
    // HA sidebar is inside nested shadow DOM, so we inject a style there
    function injectHideProfile(root) {
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) {
                // Look for the profile link or user name
                const profileLinks = el.shadowRoot.querySelectorAll(
                    'a[href="/profile"], .profile-badge, .user-badge'
                );
                for (const link of profileLinks) {
                    link.style.visibility = 'hidden';
                }
                injectHideProfile(el.shadowRoot);
            }
        }
    }
    injectHideProfile(document);
}
"""


async def anonymize_page(page: Page) -> None:
    """Inject JS to replace PII text across all shadow DOMs."""
    try:
        await page.evaluate(ANONYMIZE_JS, TEXT_REPLACEMENTS)
    except Exception as e:
        print(f"  ⚠ JS anonymize warning: {e}")
    await page.wait_for_timeout(300)
    # Run it twice — some elements may re-render after first pass
    with contextlib.suppress(Exception):
        await page.evaluate(ANONYMIZE_JS, TEXT_REPLACEMENTS)

    await page.wait_for_timeout(200)


async def screenshot(page: Page, name: str) -> Path:
    """Anonymize the page, then take a full-page screenshot."""
    await anonymize_page(page)
    path = OUTPUT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  ✓ Saved {path.relative_to(Path.cwd())}")
    return path


async def capture_element(page: Page, selector: str, name: str) -> Path | None:
    """Anonymize the page, then take a screenshot of a specific element."""
    await anonymize_page(page)
    el = page.locator(selector).first
    try:
        await el.wait_for(state="visible", timeout=10_000)
    except Exception:
        print(f"  ✗ Element '{selector}' not found, skipping {name}")
        return None
    path = OUTPUT_DIR / f"{name}.png"
    await el.screenshot(path=str(path))
    print(f"  ✓ Saved {path.relative_to(Path.cwd())}")
    return path


async def main(base_url: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,  # retina-quality screenshots
        )
        page = await context.new_page()

        # ── Step 0: Open HA and let user log in if needed ─────────────
        print(
            "\n🔑 Opening Home Assistant — log in if prompted, then press Enter here...",
        )
        await page.goto(
            f"{base_url}/config/integrations",
            wait_until="domcontentloaded",
        )
        input("   Press Enter when the Integrations page is loaded...")

        # ── Step 1: Integrations page (full) ─────────────────────────
        print("\n📸 1/10 — Integrations page (full)")
        await wait_for_ha_loaded(page)
        await screenshot(page, "01-integrations-page")

        # ── Step 2: EyeOnWater integration card close-up ─────────────
        print("\n📸 2/10 — EyeOnWater integration card")
        print("   Please search/scroll to the EyeOnWater card, then press Enter...")
        input()
        await capture_element(
            page,
            "ha-integration-card:has(ha-integration-header:has-text('EyeOnWater'))",
            "02-integration-card",
        )
        # Fallback: full page screenshot if element selector didn't match
        await screenshot(page, "02-integration-card-full")

        # ── Step 3: EyeOnWater device page (entities) ────────────────
        print("\n📸 3/10 — Device/Entities page")
        print(
            "   Please navigate to the EyeOnWater device page (click the device), then press Enter...",
        )
        input()
        await wait_for_ha_loaded(page)
        await screenshot(page, "03-device-entities")

        # ── Step 4: Options flow (Configure → unit price) ────────────
        print("\n📸 4/10 — Options flow (water cost configuration)")
        print("   Please go back to Integrations, click Configure on EyeOnWater,")
        print("   so the unit price dialog is visible, then press Enter...")
        input()
        await screenshot(page, "04-options-flow-cost")

        # ── Step 5: Energy Dashboard configuration ───────────────────
        print("\n📸 5/10 — Energy Dashboard configuration")
        await page.goto(f"{base_url}/config/energy", wait_until="domcontentloaded")
        await wait_for_ha_loaded(page)
        input("   Press Enter when the Energy config page is loaded...")
        await screenshot(page, "05-energy-dashboard-config")

        # ── Step 6: Energy Dashboard — add water consumption ─────────
        print("\n📸 6/10 — Energy Dashboard — water consumption selector")
        print(
            "   Please click 'Add water source' or expand the Water Consumption section,",
        )
        print(
            "   showing the eyeonwater:water_meter statistic picker, then press Enter...",
        )
        input()
        await screenshot(page, "06-energy-water-add")

        # ── Step 7: Energy Dashboard water consumption view ──────────
        print("\n📸 7/10 — Energy Dashboard (water consumption)")
        await page.goto(f"{base_url}/energy", wait_until="domcontentloaded")
        await wait_for_ha_loaded(page)
        input(
            "   Press Enter when the Energy dashboard is loaded with water data visible...",
        )
        await screenshot(page, "07-energy-dashboard-water")

        # ── Step 8: Developer Tools → Services (import_historical_data)
        print("\n📸 8/10 — Import Historical Data service")
        await page.goto(
            f"{base_url}/developer-tools/service",
            wait_until="domcontentloaded",
        )
        await wait_for_ha_loaded(page)
        print(
            "   Please select the 'EyeOnWater: import_historical_data' service, then press Enter...",
        )
        input()
        await screenshot(page, "08-import-historical-data")

        # ── Step 9: Sensor detail page with history graph ────────────
        print("\n📸 9/10 — Sensor detail with history graph")
        print(
            "   Please navigate to a water meter sensor (e.g. sensor.water_meter_xxxxx)",
        )
        print("   and wait for the history graph to render, then press Enter...")
        input()
        await wait_for_ha_loaded(page)
        await screenshot(page, "09-sensor-detail")

        # ── Step 10: HACS → EyeOnWater repository page ───────────────
        print("\n📸 10/10 — HACS repository page")
        print(
            "   Please navigate to HACS → Integrations → EyeOnWater, then press Enter...",
        )
        print("   (If HACS is not installed, type 'skip' and press Enter)")
        resp = input("   > ")
        if resp.strip().lower() != "skip":
            await wait_for_ha_loaded(page)
            await screenshot(page, "10-hacs-repository")

        # ── Done ──────────────────────────────────────────────────────
        print(f"\n✅ All screenshots saved to {OUTPUT_DIR.resolve()}")
        print("   You can close the browser window now.")
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture HA screenshots for docs")
    parser.add_argument("--base-url", default=BASE_URL, help="Home Assistant base URL")
    args = parser.parse_args()
    asyncio.run(main(args.base_url))
