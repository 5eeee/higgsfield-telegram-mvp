"""Render Earth Zoom AI logo PNG (1024x1024) using Pillow.

Pure-Python, no external binaries needed. Output: assets/earth-zoom-in-logo.png
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

DST = Path(__file__).resolve().parent.parent / "assets" / "earth-zoom-in-logo.png"
SIZE = 1024


def _radial_background(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    cx = cy = size / 2
    max_r = math.hypot(cx, cy)
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / max_r
            # 3-stop radial: deep blue center -> near-black edge
            t = min(1.0, d)
            r = int(26 * (1 - t) + 2 * t)
            g = int(42 * (1 - t) + 4 * t)
            b = int(94 * (1 - t) + 12 * t)
            img.putpixel((x, y), (r, g, b))
    return img


def _rounded_rect_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def _earth(size: int) -> Image.Image:
    earth = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(earth)
    cx = cy = size / 2
    # Halo
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        (cx - 220, cy - 220, cx + 220, cy + 220),
        fill=(58, 156, 255, 90),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(28))
    earth.alpha_composite(halo)

    # Earth body (radial blue gradient emulated by a few concentric circles)
    colors = [
        (18, 51, 122),
        (40, 96, 195),
        (58, 156, 255),
        (138, 228, 255),
    ]
    radii = [175, 150, 120, 80]
    offsets = [(0, 0), (-6, -8), (-12, -16), (-20, -26)]
    for color, r, (ox, oy) in zip(colors, radii, offsets, strict=True):
        d.ellipse((cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r), fill=color)

    # Continents (stylised green shapes)
    green_a = (47, 208, 138, 235)
    green_b = (55, 227, 154, 240)
    green_c = (42, 184, 126, 225)
    d.ellipse((cx - 86, cy - 58, cx - 22, cy + 10), fill=green_a)
    d.ellipse((cx + 48, cy - 82, cx + 120, cy + 7), fill=green_b)
    d.ellipse((cx + 20, cy + 54, cx + 94, cy + 149), fill=green_c)
    return earth


def _zoom_rings(size: int) -> Image.Image:
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx = cy = size / 2
    rings = [
        (440, (158, 219, 255, 40)),
        (390, (135, 204, 255, 55)),
        (340, (93, 162, 255, 85)),
        (276, (74, 120, 230, 140)),
        (220, (106, 154, 255, 180)),
    ]
    for r, color in rings:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=3)
    return overlay


def _zoom_trails(size: int) -> Image.Image:
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Diagonal zoom streaks
    for width, alpha in [(44, 140), (18, 100)]:
        d.line(
            [(180, 870), (860, 200)],
            fill=(110, 224, 255, alpha),
            width=width,
        )
    return overlay.filter(ImageFilter.GaussianBlur(6))


def _stars(size: int) -> Image.Image:
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    stars = [
        (820, 220, 3, 230),
        (780, 300, 2, 180),
        (880, 360, 2, 210),
        (200, 240, 2, 180),
        (150, 640, 3, 210),
        (260, 820, 2, 150),
        (700, 820, 2, 150),
        (340, 160, 2, 160),
        (640, 180, 2, 160),
    ]
    for x, y, r, a in stars:
        d.ellipse((x - r, y - r, x + r, y + r), fill=(223, 245, 255, a))
    return overlay


def _focus_dot(size: int) -> Image.Image:
    """Small bright focus point over the Earth — 'zoom target' metaphor."""
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx = cy = size / 2
    # Crosshair reticle: outer thin ring + small center dot
    d.ellipse((cx - 40, cy - 40, cx + 40, cy + 40), outline=(242, 248, 255, 170), width=2)
    d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=(242, 248, 255, 230))
    # Tiny tick marks
    for dx, dy in [(-58, 0), (58, 0), (0, -58), (0, 58)]:
        d.line(
            [(cx + dx - 10 * (1 if dx == 0 else dx / abs(dx) if dx else 0),
              cy + dy - 10 * (1 if dy == 0 else dy / abs(dy) if dy else 0)),
             (cx + dx + 10 * (1 if dx == 0 else dx / abs(dx) if dx else 0),
              cy + dy + 10 * (1 if dy == 0 else dy / abs(dy) if dy else 0))],
            fill=(242, 248, 255, 150),
            width=3,
        )
    return overlay


def render() -> None:
    bg = _radial_background(SIZE)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    canvas.paste(bg.convert("RGBA"))

    canvas.alpha_composite(_stars(SIZE))
    canvas.alpha_composite(_zoom_trails(SIZE))
    canvas.alpha_composite(_zoom_rings(SIZE))
    canvas.alpha_composite(_earth(SIZE))
    canvas.alpha_composite(_focus_dot(SIZE))

    # Round corners
    mask = _rounded_rect_mask(SIZE, radius=228)
    rounded = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    rounded.paste(canvas, (0, 0), mask)

    rounded.save(DST, format="PNG")
    print(f"Saved {DST} ({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    render()
