"""Quick analyzer for motions_full.json to categorize 121 Higgsfield presets."""
import json
from collections import defaultdict

items = json.load(open('motions_full.json','r',encoding='utf-8'))

print(f'Total motions: {len(items)}')
start_end = [i for i in items if i['start_end_frame']]
print(f'start_end_frame=True: {len(start_end)} (need 2 images)')
print(f'start_end_frame=False: {len(items)-len(start_end)} (need 1 image)')
print()

# Find key motions by keyword
KEYWORDS = {
    'zoom_earth': ['earth', 'zoom', 'planet', 'space', 'orbit', 'globe'],
    'camera': ['pan', 'tilt', 'dolly', 'crane', 'tracking', 'follow', 'truck', 'arc', 'handheld', 'steadicam', 'push', 'pull', 'crash', 'roll', 'whip'],
    'action': ['run', 'punch', 'kick', 'fight', 'jump', 'fly', 'fall', 'chase', 'attack', 'dodge'],
    'explosion': ['explosion', 'explode', 'burst', 'blast', 'implode'],
    'transform': ['transform', 'morph', 'clone', 'split', 'multiply', 'shatter', 'melt', 'freeze'],
    'dance': ['dance', 'moonwalk', 'catwalk', 'walk', 'spin', 'twist'],
    'vfx': ['soul', 'ghost', 'magic', 'glow', 'particle', 'laser', 'fire', 'smoke', 'portal'],
    'cinematic': ['cinematic', 'dramatic', 'slow motion', 'reveal', 'title', 'opening'],
}

cat_map = defaultdict(list)
for it in items:
    name = (it.get('name') or '').lower()
    desc = (it.get('description') or '').lower()
    text = f'{name} {desc}'
    placed = False
    for cat, kws in KEYWORDS.items():
        if any(k in text for k in kws):
            cat_map[cat].append(it)
            placed = True
            break
    if not placed:
        cat_map['other'].append(it)

for cat, lst in cat_map.items():
    print(f'\n=== {cat.upper()} ({len(lst)}) ===')
    for it in lst:
        flag = 'S+E' if it['start_end_frame'] else ' S '
        print(f'  [{flag}] {it["name"]:25s}  {(it.get("description") or "")[:70]}')
