"""
Generate input.jsonl for all pairwise single-character comparisons.

Alphabet: a-z, A-Z, 0-9  (62 chars)
Fonts:    1 regular + 1 monospace
Pairs:    C(62,2) × 2 fonts = 3,782
"""

import json
import string
from itertools import combinations
from pathlib import Path

CHARS = list(string.ascii_lowercase + string.ascii_uppercase + string.digits)
FONTS = ["Roboto", "Roboto Mono"]

out_dir = Path(__file__).resolve().parent.parent / "jobs" / "001-all-chars"
out_dir.mkdir(parents=True, exist_ok=True)

pairs = []
for font in FONTS:
    for a, b in combinations(CHARS, 2):
        pairs.append({"a": a, "b": b, "font": font})

out_path = out_dir / "input.jsonl"
with open(out_path, "w") as f:
    for p in pairs:
        f.write(json.dumps(p) + "\n")

print(f"Chars:  {len(CHARS)}")
print(f"Fonts:  {len(FONTS)}")
print(f"Pairs:  {len(pairs)}")
print(f"Wrote:  {out_path}")
