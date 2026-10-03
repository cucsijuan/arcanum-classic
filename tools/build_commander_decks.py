#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds commander starter decks from cards the engine fully supports.

Usage: tools/build_commander_decks.py <card-file.jsonl[.gz]>

For each color in COLORS: picks the strongest supported mono-colored legendary creature as commander, then 62
supported nonland cards of that color (singleton, legal in commander, a reasonable mana curve, mostly creatures)
and 37 basic lands. Writes decks/commander-<color>.txt.
"""
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from generate_scripts import ENGINE_KEYWORDS, DERIVED_LINE, is_keyword_line  # noqa: E402

COLORS = {"G": ("green", "Forest"), "R": ("red", "Mountain"), "W": ("white", "Plains"), "B": ("black", "Swamp"), "U": ("blue", "Island")}
CURVE = {1: 6, 2: 14, 3: 14, 4: 12, 5: 9, 6: 5, 7: 2}  # nonland slots by mana value (7 = 7+)


def scripted_ids():
    out = set()
    for f in os.listdir(os.path.join(ROOT, "scripts")):
        if f.endswith(".json"):
            out.add(f[:-5])
    return out


def supported(card, scripts):
    if card.get("layout") != "normal":
        return False
    if any(k.lower() not in ENGINE_KEYWORDS for k in card.get("keywords", [])):
        return False
    for stat in ("power", "toughness"):
        if stat in card and not re.fullmatch(r"-?\d+", card[stat]):
            return False
    if re.search(r"\{X\}|/", card.get("mana_cost", "")):
        return False
    if card["oracle_id"] in scripts:
        return True
    text = re.sub(r"\s*\([^)]*\)", "", card.get("oracle_text", ""))
    for line in [l.strip().rstrip(".") for l in text.split("\n") if l.strip()]:
        if DERIVED_LINE.fullmatch(line) or is_keyword_line(line, card.get("keywords", [])):
            continue
        return False
    return True


def value(card):
    p = int(card.get("power", "0") or 0)
    t = int(card.get("toughness", "0") or 0)
    return p * 1.5 + t + len(card.get("keywords", [])) + (2 if card["oracle_id"] in SCRIPTS else 0)


SCRIPTS = set()


def main():
    global SCRIPTS
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    SCRIPTS = scripted_ids()
    opener = gzip.open if sys.argv[1].endswith(".gz") else open
    pool = []
    with opener(sys.argv[1], "rt", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c.get("legalities", {}).get("commander") != "legal" or "Token" in c.get("type_line", ""):
                continue
            if supported(c, SCRIPTS):
                pool.append(c)
    for color, (word, basic) in COLORS.items():
        mono = [c for c in pool if c.get("color_identity") == [color]]
        legends = [c for c in mono if "Legendary" in c.get("type_line", "") and "Creature" in c.get("type_line", "")]
        if not legends:
            print(f"no supported {word} commander")
            continue
        commander = max(legends, key=lambda c: (value(c), -c.get("cmc", 0)))
        nonland = [c for c in mono if "Land" not in c.get("type_line", "") and c["oracle_id"] != commander["oracle_id"]]
        picked = []
        for mv, slots in CURVE.items():
            bucket = [c for c in nonland if (int(c.get("cmc", 0)) == mv if mv < 7 else int(c.get("cmc", 0)) >= 7)]
            creatures = sorted([c for c in bucket if "Creature" in c["type_line"]], key=value, reverse=True)
            spells = sorted([c for c in bucket if "Creature" not in c["type_line"]], key=lambda c: c["oracle_id"] in SCRIPTS, reverse=True)
            n_spells = slots // 3
            take = creatures[: slots - n_spells] + spells[:n_spells]
            picked += take[:slots]
        names = {c["name"] for c in picked}
        # Top up with the best remaining cards if some buckets were short.
        for c in sorted(nonland, key=value, reverse=True):
            if len(picked) >= 62:
                break
            if c["name"] not in names:
                picked.append(c)
                names.add(c["name"])
        if len(picked) < 62:
            print(f"only {len(picked)} supported {word} cards; skipping")
            continue
        path = os.path.join(ROOT, "decks", f"commander-{word}.txt")
        with open(path, "w", encoding="utf-8") as out:
            out.write(f"# Commander starter deck ({word}), built from fully supported cards.\n")
            out.write(f"Commander\n1 {commander['name']}\n\nDeck\n")
            for c in sorted(picked[:62], key=lambda c: (c.get("cmc", 0), c["name"])):
                out.write(f"1 {c['name']}\n")
            out.write(f"37 {basic}\n")
        print(f"{word}: {commander['name']} + {len(picked[:62])} cards -> {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
