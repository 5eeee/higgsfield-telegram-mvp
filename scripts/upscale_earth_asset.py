"""Upscale Earth asset to 1104x1472 (HD portrait) to match the reference.

The reference share (https://higgsfield.ai/s/28TKrUxP9Bk) renders at 834x1112,
but DoP output resolution follows the smaller of its input images. To get
an HD output (1104x1472-ish), BOTH inputs (Earth + face) must be >= HD.
"""
from pathlib import Path
from PIL import Image

SRC = Path("assets/earth_reference.jpg")
DST = Path("assets/earth_reference.jpg")

TARGET_W, TARGET_H = 1152, 1536  # 3:4 portrait @ ~2x the ref

img = Image.open(SRC).convert("RGB")
w, h = img.size
print(f"source: {w}x{h}")
if w >= TARGET_W and h >= TARGET_H:
    print("already >= target, leaving")
else:
    # High-quality bicubic upscale, then sharpen.
    img = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    from PIL import ImageFilter
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
    img.save(DST, quality=96, optimize=True)
    print(f"saved {DST}: {img.size}")
