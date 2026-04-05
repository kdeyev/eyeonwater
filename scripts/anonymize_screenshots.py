r"""Post-process anonymization for EyeOnWater documentation screenshots.

This is the second pass after Playwright's JS-based text replacement.
It handles pixel-level blurring for areas that can't be anonymized via DOM:
- Username avatar (bottom-left sidebar)
- Other integration cards (integrations page)
- Other HACS repositories
- Sidebar custom items that reveal the user's setup

Usage:
    .venv\Scripts\python.exe scripts/anonymize_screenshots.py

Input:  docs/img/  (screenshots with text already replaced by Playwright)
Output: docs/img/  (overwritten with blurred versions)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

IMG_DIR = Path(__file__).resolve().parent.parent / "docs" / "img"

# Device scale factor used during capture (2x retina)
SCALE = 2


# ─── Redaction definitions ────────────────────────────────────────────
# All coordinates are in ACTUAL PIXELS (already scaled).
# The images are 2560x1800 (1280x900 CSS * 2x scale).


def _r(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Convert CSS-pixel rect to actual-pixel box (x1,y1,x2,y2)."""
    return (x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE)


# Each screenshot gets a list of operations
REDACTIONS: dict[str, list[dict]] = {
    # ── 01: Integrations page ──────────────────────────────────────
    # Blur all integration cards EXCEPT EyeOnWater row
    "01-integrations-page": [
        # User avatar + name at bottom-left
        {"box": _r(0, 858, 260, 42), "action": "blur"},
        # Top 3 rows of integration cards (above EyeOnWater row)
        {"box": _r(280, 95, 1010, 470), "action": "blur"},
        # Bottom rows (below EyeOnWater row)
        {"box": _r(280, 700, 1010, 250), "action": "blur"},
    ],
    # ── 02: Integration card full ──────────────────────────────────
    "02-integration-card-full": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
        # Top rows
        {"box": _r(280, 95, 1010, 530), "action": "blur"},
        # Bottom rows
        {"box": _r(280, 760, 1010, 200), "action": "blur"},
    ],
    # ── 03: Device/entities page ───────────────────────────────────
    "03-device-entities": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 04: Options flow ───────────────────────────────────────────
    "04-options-flow-cost": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 05: Energy dashboard config ────────────────────────────────
    "05-energy-dashboard-config": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 06: Energy water add dialog ────────────────────────────────
    "06-energy-water-add": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 07: Energy dashboard water ─────────────────────────────────
    "07-energy-dashboard-water": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 08: Import historical data ─────────────────────────────────
    "08-import-historical-data": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 09: Sensor detail ──────────────────────────────────────────
    "09-sensor-detail": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
    ],
    # ── 10: HACS repository ────────────────────────────────────────
    "10-hacs-repository": [
        {"box": _r(0, 858, 260, 42), "action": "blur"},
        # Blur all rows except Eye On Water (the "Downloaded" section)
        {"box": _r(280, 290, 1010, 620), "action": "blur"},
    ],
}


def apply_redactions(img: Image.Image, redactions: list[dict]) -> Image.Image:
    """Apply blur/fill redactions to an image."""
    for r in redactions:
        box = r["box"]
        # Clamp to image bounds
        box = (
            max(0, box[0]),
            max(0, box[1]),
            min(img.width, box[2]),
            min(img.height, box[3]),
        )

        if r["action"] == "blur":
            region = img.crop(box)
            region = region.filter(ImageFilter.GaussianBlur(radius=20))
            img.paste(region, box)

        elif r["action"] == "fill":
            draw = ImageDraw.Draw(img)
            color = r.get("color", (255, 255, 255))
            draw.rectangle(box, fill=color)

    return img

    return img


def main():
    print(f"Anonymizing screenshots in {IMG_DIR}")
    processed = 0
    skipped = 0

    for name, redactions in REDACTIONS.items():
        path = IMG_DIR / f"{name}.png"
        if not path.exists():
            print(f"  SKIP {name}.png (not found)")
            skipped += 1
            continue

        img = Image.open(path)
        img = apply_redactions(img, redactions)
        img.save(path)
        print(f"  OK   {name}.png ({len(redactions)} redactions)")
        processed += 1

    print(f"\nDone: {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    main()
