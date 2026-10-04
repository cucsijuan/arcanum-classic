#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds a 360-card singleton cube from cards the engine fully supports.

Usage: tools/build_cube.py <card-file.jsonl[.gz]> [name]

55 cards of each color (with a draft-friendly curve and about 60% creatures), 3 of each two-color pair,
25 colorless cards and 25 lands that make two colors. Popular cards (by the card source's popularity rank) are
preferred. Writes cubes/<name>.txt (default: classic).
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from build_commander_decks import scripted_ids, supported  # noqa: E402

COLORS = "WUBRG"
PER_COLOR = 55
CURVE = {1: 7, 2: 14, 3: 12, 4: 10, 5: 7, 6: 5}  # by mana value (6 = 6+)
CREATURE_SHARE = 0.6
PER_PAIR = 3
COLORLESS = 25
LANDS = 25


def rank(card):
    return card.get("edhrec_rank") or 10**7


def mv_slot(card):
    return max(1, min(6, int(card.get("cmc", 0))))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    name = sys.argv[2] if len(sys.argv) > 2 else "classic"
    scripts = scripted_ids()
    opener = gzip.open if sys.argv[1].endswith(".gz") else open
    pool = []
    with opener(sys.argv[1], "rt", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c.get("legalities", {}).get("vintage") != "legal" or "Token" in c.get("type_line", ""):
                continue
            if "Basic" in c.get("type_line", "") or not supported(c, scripts):
                continue
            pool.append(c)
    pool.sort(key=rank)

    cube = []
    taken = set()

    def take(cards, count):
        for c in cards:
            if count <= 0:
                break
            if c["name"] in taken:
                continue
            taken.add(c["name"])
            cube.append(c)
            count -= 1
        return count

    for color in COLORS:
        mono = [c for c in pool if c.get("colors") == [color] and "Land" not in c["type_line"]]
        for slot, n in CURVE.items():
            in_slot = [c for c in mono if mv_slot(c) == slot]
            creatures = int(round(n * CREATURE_SHARE))
            left = take([c for c in in_slot if "Creature" in c["type_line"]], creatures)
            left = take([c for c in in_slot if "Creature" not in c["type_line"]], n - creatures + left)
            take(in_slot, left)
    for i, a in enumerate(COLORS):
        for b in COLORS[i + 1:]:
            pair = [c for c in pool if sorted(c.get("colors", [])) == sorted([a, b]) and "Land" not in c["type_line"]]
            take(pair, PER_PAIR)
    take([c for c in pool if not c.get("colors") and "Land" not in c["type_line"]], COLORLESS)
    duals = [c for c in pool if "Land" in c["type_line"] and len(set(c.get("produced_mana", [])) & set(COLORS)) == 2]
    take(duals, LANDS)
    # A category short of cards (few supported cards of a pair, say): fill up with the next most popular cards.
    take([c for c in pool if "Land" not in c["type_line"] and len(c.get("colors", [])) <= 1], 360 - len(cube))

    os.makedirs(os.path.join(ROOT, "cubes"), exist_ok=True)
    path = os.path.join(ROOT, "cubes", f"{name}.txt")
    with open(path, "w", encoding="utf-8") as out:
        out.write(f"# {name}: {len(cube)}-card singleton cube of supported cards, built by tools/build_cube.py\n")
        for c in sorted(cube, key=lambda c: (c.get("colors") or ["Z"], c.get("cmc", 0), c["name"])):
            out.write(f"1 {c['name']}\n")
    print(f"{len(cube)} cards -> {path}")


if __name__ == "__main__":
    sys.exit(main())
