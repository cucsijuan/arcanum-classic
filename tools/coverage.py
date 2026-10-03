#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Reports how much of a card set the engine supports.

Usage:
    tools/coverage.py <card-file.jsonl[.gz]> <sets/code.json> [--list] [--lines N]

A card is supported when it has a script (or needs none) and uses only keywords and costs the engine
implements. Prints the share supported, the unsupported cards with --list, and the N most common rules-text
lines among unsupported cards (default 40) to show what to implement next.
"""
import gzip
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_commander_decks import scripted_ids, supported  # noqa: E402
from generate_scripts import Unsupported, generate  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 1
    top = 40
    if "--lines" in sys.argv:
        top = int(sys.argv[sys.argv.index("--lines") + 1])
        args = [a for a in args if a != str(top)]
    with open(args[1], encoding="utf-8") as f:
        wanted = set(json.load(f)["cards"])
    scripts = scripted_ids()
    opener = gzip.open if args[0].endswith(".gz") else open
    found, missing_lines, unsupported = {}, Counter(), []
    with opener(args[0], "rt", encoding="utf-8") as f:
        for line in f:
            card = json.loads(line)
            if card["name"] not in wanted or "Token" in card.get("type_line", ""):
                continue
            found[card["name"]] = card
    for name in sorted(found):
        card = found[name]
        if supported(card, scripts):
            continue
        unsupported.append(name)
        try:
            generate(card)
            reason = "(generator understands it: run generate_scripts.py)"
        except Unsupported as e:
            reason = str(e)
        missing_lines[re.sub(r"\b\d+\b", "N", reason)] += 1
    total = len(found)
    ok = total - len(unsupported)
    print(f"{ok}/{total} supported ({100 * ok / max(total, 1):.1f}%), {len(wanted) - total} not found in card data")
    if "--list" in sys.argv:
        for name in unsupported:
            print("  " + name)
    print("\nmost common blocking lines (first line the generator does not understand):")
    for text, n in missing_lines.most_common(top):
        print(f"{n:4} {text}")


if __name__ == "__main__":
    sys.exit(main())
