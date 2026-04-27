"""Generate src/presets.py from motions_full.json with categorization + engine hints.

Run once after pulling a fresh motions dump; the output file is committed.
"""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOTIONS_FILE = REPO / "motions_full.json"
OUTPUT = REPO / "src" / "presets.py"

CATEGORIES: dict[str, dict[str, object]] = {
    "earth_zoom": {
        "label": "🌍 Earth Zoom / Cosmic",
        "emoji": "🌍",
        "keywords": [
            "earth zoom out", "hyperlapse", "fpv drone", "zoom in", "zoom out",
            "crash zoom in", "crash zoom out", "yoyo zoom", "dolly zoom in",
            "dolly zoom out", "super dolly in", "super dolly out", "mouth in",
            "eyes in", "through object in", "through object out",
        ],
    },
    "camera": {
        "label": "🎥 Camera Movement",
        "emoji": "🎥",
        "keywords": [
            "360 orbit", "arc left", "arc right", "dolly in", "dolly out",
            "dolly left", "dolly right", "double dolly", "crane up", "crane down",
            "crane over the head", "tilt up", "tilt down", "jib up", "jib down",
            "handheld", "static", "whip pan", "overhead", "head tracking",
            "lazy susan", "focus change", "robo arm", "dutch angle",
            "roll transition", "snorricam", "wiggle", "rap flex", "fisheye",
            "general", "steadicam",
        ],
    },
    "action": {
        "label": "⚡ Action & Sports",
        "emoji": "⚡",
        "keywords": [
            "action run", "baseball kick", "basketball dunks", "boxing",
            "car chasing", "catwalk", "face punch", "flying", "skateboard ollie",
            "skateboard glide", "skate cruise", "snowboard carving",
            "snowboard powder", "ski carving", "ski powder", "soul jump",
            "downhill pov", "car grip", "object pov", "buckle up", "incline",
            "push to glass", "wind to face",
        ],
    },
    "explosion": {
        "label": "💥 Explosions & VFX",
        "emoji": "💥",
        "keywords": [
            "building explosion", "car explosion", "clone explosion",
            "head explosion", "powder explosion", "paparazzi", "sand storm",
            "set on fire", "fire breathe", "paint splash", "flood",
        ],
    },
    "transform": {
        "label": "🪄 Transform & Morph",
        "emoji": "🪄",
        "keywords": [
            "agent reveal", "bullet time", "diamond", "duplicate", "floral eyes",
            "glowshift", "innerlight", "medusa gorgona", "melting", "morphskin",
            "thunder god", "turning metal", "freezing", "skin surge",
            "disintegration", "invisible", "levitation", "tentacles",
            "bloom mouth", "angel wings", "garden bloom", "head off",
            "black tears",
        ],
    },
    "dance": {
        "label": "💃 Dance & Performance",
        "emoji": "💃",
        "keywords": [
            "moonwalk left", "moonwalk right", "3d rotation", "timelapse human",
            "kiss", "glam",
        ],
    },
    "lens": {
        "label": "🎞️ Lens & Film Effects",
        "emoji": "🎞️",
        "keywords": [
            "lens flare", "lens crack", "dirty lens", "datamosh", "low shutter",
            "super 8mm", "vhs", "timelapse landscape", "abstract",
        ],
    },
    "ambient": {
        "label": "🌊 Ambient VFX",
        "emoji": "🌊",
        "keywords": ["floating fish", "glowing fish", "jelly drift"],
    },
}


def classify(name: str, description: str) -> str:
    nlow = name.lower()
    for cat_key, meta in CATEGORIES.items():
        for kw in meta["keywords"]:  # type: ignore[index]
            if kw.lower() == nlow:
                return cat_key
    # fallback: substring match
    text = f"{name} {description}".lower()
    for cat_key, meta in CATEGORIES.items():
        for kw in meta["keywords"]:  # type: ignore[index]
            if kw.lower() in text:
                return cat_key
    return "camera"  # safe default


ENGINE_POLICY = {
    # start_end_frame=True motions → DoP (trained on keyframe pairs).
    # start_end_frame=False → Seedance (face preservation, full scene animation).
    # Exception: Earth Zoom family → always DoP, since they were designed there.
    "earth_zoom": ("dop", "dop-preview"),
    "camera": ("dop", "dop-preview"),
    "action": ("dop", "dop-preview"),
    "explosion": ("dop", "dop-preview"),
    "transform": ("dop", "dop-preview"),
    "dance": ("dop", "dop-preview"),
    "lens": ("dop", "dop-preview"),
    "ambient": ("seedance", "seedance_lite"),
}


def emoji_for(cat: str) -> str:
    return str(CATEGORIES[cat]["emoji"])


def build_prompt(name: str, description: str) -> str:
    base = description.strip().rstrip(".")
    if not base:
        base = f"A cinematic {name} shot"
    prompt = (
        f"Photorealistic cinematic shot: {base}. The same person from the "
        f"reference photo, their exact face and features preserved 1-to-1 "
        f"— no morphing, no cartoon, no stylization. Hyper-realistic, sharp "
        f"detail, dramatic lighting, Hollywood blockbuster quality, 8K."
    )
    return prompt


def escape_triple_quoted(text: str) -> str:
    text = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return text


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "unnamed"


def main() -> None:
    raw = json.loads(MOTIONS_FILE.read_text(encoding="utf-8"))
    seen_slugs: set[str] = set()
    entries: list[dict] = []
    for motion in raw:
        name = (motion.get("name") or "").strip()
        desc = (motion.get("description") or "").strip()
        uid = motion.get("id")
        if not (name and uid):
            continue
        cat = classify(name, desc)
        engine, model = ENGINE_POLICY[cat]
        slug = slugify(name)
        base_slug = slug
        counter = 2
        while slug in seen_slugs:
            slug = f"{base_slug}_{counter}"
            counter += 1
        seen_slugs.add(slug)
        entries.append({
            "slug": slug,
            "name": name,
            "category": cat,
            "motion_id": uid,
            "description": desc,
            "start_end_frame": bool(motion.get("start_end_frame")),
            "engine": engine,
            "model": model,
            "prompt": build_prompt(name, desc),
            "preview_url": motion.get("preview_url"),
        })

    # Order: Earth first, then categories by our declared order
    cat_order = list(CATEGORIES.keys())
    entries.sort(key=lambda e: (cat_order.index(e["category"]), e["name"]))

    # Codegen
    header = '''"""FULL catalog of Higgsfield motion presets — all 121 motions from /v1/motions.

This file is auto-generated by ``scripts/build_presets.py`` from a live dump of
the Higgsfield motion catalog (``motions_full.json``). Each entry carries the
metadata needed to fire off a render in the right engine with the right
defaults, without asking the user anything beyond "which preset?".

Categories:
''' + "\n".join(f'  * {k}: {v["label"]}' for k, v in CATEGORIES.items()) + '''

Engine routing rules (see scripts/build_presets.py::ENGINE_POLICY):
  * Earth Zoom / Camera / Action / Explosion / Transform / Dance / Lens → DoP preview
  * Ambient VFX (fish, jelly) → Seedance Lite (single-image, face preservation)

Dual-frame motions (``start_end_frame = True``) accept start + end keyframes.
For those we default to reusing the user's photo on both ends, which gives a
stable camera movement around the subject. Earth Zoom In is a special case:
it uses a Soul-generated Earth shot as the **start** frame and the user's
face as the **end** frame — see src/bot.py::EARTH_ZOOM_IN_* constants.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class VfxPreset:
    slug: str
    name: str
    category: str
    motion_id: str
    description: str
    start_end_frame: bool
    engine: str            # 'dop' | 'seedance' | 'kling' | 'minimax'
    model: str             # engine-specific model id
    duration_seconds: int  # recommended render length
    prompt: str
    preview_url: str | None = None


CATEGORY_LABELS: Final[dict[str, str]] = {
'''
    body_lines: list[str] = []
    body_lines.append(header)
    for key, meta in CATEGORIES.items():
        body_lines.append(f'    "{key}": "{meta["label"]}",')
    body_lines.append("}\n\n")
    body_lines.append("PRESETS: Final[tuple[VfxPreset, ...]] = (\n")
    for e in entries:
        # Recommended duration per engine.
        if e["engine"] == "dop":
            duration = 5  # DoP renders 5s fast, 10s is 2× time — keep snappy.
        elif e["engine"] == "seedance":
            duration = 5
        elif e["engine"] == "kling":
            duration = 5
        else:
            duration = 6
        name_escaped = e["name"].replace('"', '\\"')
        description_escaped = e["description"].replace('"', '\\"').replace("\n", " ")
        prompt_escaped = e["prompt"].replace('"', '\\"').replace("\n", " ")
        preview_line = (
            f'        preview_url="{e["preview_url"]}",'
            if e.get("preview_url") else "        preview_url=None,"
        )
        body_lines.append(textwrap.dedent(f'''\
    VfxPreset(
        slug="{e["slug"]}",
        name="{name_escaped}",
        category="{e["category"]}",
        motion_id="{e["motion_id"]}",
        description="{description_escaped}",
        start_end_frame={e["start_end_frame"]},
        engine="{e["engine"]}",
        model="{e["model"]}",
        duration_seconds={duration},
        prompt=(
            "{prompt_escaped}"
        ),
{preview_line}
    ),
'''))
    body_lines.append(")\n\n")

    body_lines.append("_BY_SLUG: Final[dict[str, VfxPreset]] = {p.slug: p for p in PRESETS}\n\n")
    body_lines.append("_BY_CATEGORY: Final[dict[str, tuple[VfxPreset, ...]]] = {\n")
    for cat in CATEGORIES:
        body_lines.append(f'    "{cat}": tuple(p for p in PRESETS if p.category == "{cat}"),\n')
    body_lines.append("}\n\n")

    body_lines.append('''def preset_by_slug(slug: str) -> VfxPreset | None:
    return _BY_SLUG.get(slug)


def presets_in_category(category: str) -> tuple[VfxPreset, ...]:
    return _BY_CATEGORY.get(category, ())


def categories() -> tuple[str, ...]:
    return tuple(CATEGORY_LABELS.keys())


def preset_count() -> int:
    return len(PRESETS)


def random_preset(rng: random.Random | None = None) -> VfxPreset:
    chooser = rng or random
    return chooser.choice(PRESETS)


# Slug of the flagship Earth Zoom In scenario. We reuse the "Earth Zoom Out"
# motion but reverse its keyframe roles: Earth as start, face as end — the
# motion keeps its trained trajectory, so we get a clean Earth → face zoom.
EARTH_ZOOM_IN_MOTION_SLUG = "earth_zoom_out"
''')

    OUTPUT.write_text("".join(body_lines), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(entries)} presets")

    # Sanity check — print counts per category
    from collections import Counter
    counts = Counter(e["category"] for e in entries)
    for cat in CATEGORIES:
        print(f"  {cat}: {counts.get(cat, 0)}")


if __name__ == "__main__":
    main()
