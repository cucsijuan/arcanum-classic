#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds two-color sample decks from a card set, using only cards the engine supports.

Usage: tools/build_set_decks.py <card-file.jsonl[.gz]> <sets/code.json>

For each color pair: 36 nonland cards of those colors (or colorless) from the set, favoring creatures and a
reasonable curve, 22 creatures and 14 other spells when possible, one copy each (two when the pool is short), plus 12 + 12 basic lands.
Writes decks/<code>-<pair>.txt.
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from build_commander_decks import scripted_ids, supported  # noqa: E402

PAIRS = {"WU": ("Plains", "Island"), "UB": ("Island", "Swamp"), "BR": ("Swamp", "Mountain"),
         "RG": ("Mountain", "Forest"), "GW": ("Forest", "Plains")}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    with open(sys.argv[2], encoding="utf-8") as f:
        set_info = json.load(f)
    wanted = set(set_info["cards"])
    scripts = scripted_ids()
    opener = gzip.open if sys.argv[1].endswith(".gz") else open
    pool = []
    with opener(sys.argv[1], "rt", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c["name"] in wanted and "Land" not in c.get("type_line", "") and "Token" not in c.get("type_line", "") and supported(c, scripts):
                pool.append(c)
    for pair, (a, b) in PAIRS.items():
        cards = [c for c in pool if set(c.get("color_identity", [])) <= set(pair) and c.get("color_identity")]
        cards += [c for c in pool if not c.get("color_identity")][:4]
        key = lambda c: (c.get("cmc", 0) > 5, c.get("cmc", 0), c["name"])
        creatures = sorted([c for c in cards if "Creature" in c["type_line"]], key=key)
        others = sorted([c for c in cards if "Creature" not in c["type_line"]], key=key)
        picks = creatures[:22] + others[:14]
        picks += [c for c in creatures[22:] + others[14:]][: 36 - len(picks)]
        copies = 1 if len(picks) >= 36 else 2
        lines = []
        total = 0
        for c in picks:
            if total >= 36:
                break
            n = min(copies, 36 - total)
            lines.append(f"{n} {c['name']}")
            total += n
        lines += [f"{12 + (36 - total) // 2} {a}", f"{12 + (36 - total + 1) // 2} {b}"]
        path = os.path.join(ROOT, "decks", f"{set_info['code']}-{pair.lower()}.txt")
        with open(path, "w", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
        print(f"{pair}: {total} nonland cards from {len(cards)} candidates -> {path}")


if __name__ == "__main__":
    sys.exit(main())
