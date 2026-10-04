#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds two-color sample decks from a card set, using only cards the engine supports.

Usage: tools/build_set_decks.py <card-file.jsonl[.gz]> <sets/code.json> [<printings-file.jsonl[.gz]>]

For each color pair: 36 nonland cards of those colors (or colorless) from the set, favoring creatures and a
reasonable curve, 22 creatures and 14 other spells when possible, one copy each (two when the pool is short), plus 12 + 12 basic lands.
Writes decks/<code>-<pair>.txt. With the printings file every line names the card's printing in the set
("1 Name (CODE) 123"), so the decks show that set's art; basic lands come from the set too.
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


def set_printings(path, code):
    """name -> collector number of the card's printing in the set (the booster one, lowest number first)."""
    opener = gzip.open if path.endswith(".gz") else open
    found = {}
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if f'"set":"{code}"' not in line.replace(" ", ""):
                continue
            c = json.loads(line)
            if c.get("set") != code or c.get("lang", "en") != "en":
                continue
            digits = "".join(ch for ch in c["collector_number"] if ch.isdigit())
            rank = (not c.get("booster", False), int(digits) if digits else 10**9)
            if c["name"] not in found or rank < found[c["name"]][0]:
                found[c["name"]] = (rank, c["collector_number"])
    return {name: number for name, (_, number) in found.items()}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    with open(sys.argv[2], encoding="utf-8") as f:
        set_info = json.load(f)
    wanted = set(set_info["cards"])
    numbers = set_printings(sys.argv[3], set_info["code"]) if len(sys.argv) > 3 else {}

    def deck_line(count, name):
        if name in numbers:
            return f"{count} {name} ({set_info['code'].upper()}) {numbers[name]}"
        if numbers:
            raise SystemExit(f"{name} has no printing in {set_info['code']}")
        return f"{count} {name}"
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
            lines.append(deck_line(n, c["name"]))
            total += n
        lines += [deck_line(12 + (36 - total) // 2, a), deck_line(12 + (36 - total + 1) // 2, b)]
        path = os.path.join(ROOT, "decks", f"{set_info['code']}-{pair.lower()}.txt")
        with open(path, "w", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
        print(f"{pair}: {total} nonland cards from {len(cards)} candidates -> {path}")


if __name__ == "__main__":
    sys.exit(main())
