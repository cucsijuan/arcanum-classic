#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Sums up a set's 17Lands public game data (CC BY 4.0, https://www.17lands.com/public_datasets) by archetype.

Usage: tools/archetype_stats.py <set code> [<set code>...] [--format PremierDraft] [--cache <dir>]

Reads game_data_public.<SET>.<format>.csv.gz from the cache folder (default ~/.cache/arcanum/17lands; tools/draft_ratings.py
downloads it) and writes archetypes.<set>.json next to it. An archetype is a deck's main colors (two or three colors; splashes are
ignored). For each archetype: games and wins, and for each card:
- gih / gihWins: the games where the card was in hand (opening hand or drawn) and how many of them were won;
- copies: the copies in the decks of all its games, top: the copies in the decks of the stronger players' games (a game win
  rate of TOP_BUCKET or more), topGames: how many games those are.
tools/build_archetype_decks.py builds the decks from it. Sets run in parallel, one process each.
"""
import csv
import gzip
import json
import os
import sys
from multiprocessing import Pool

CACHE = os.path.expanduser("~/.cache/arcanum/17lands")
TOP_BUCKET = 0.58
ZERO = ("0", "0.0", "")

csv.field_size_limit(sys.maxsize)


def summarize(args):
    code, fmt, cache = args
    path = os.path.join(cache, f"game_data_public.{code.upper()}.{fmt}.csv.gz")
    out = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        head = next(reader)
        col = {h: i for i, h in enumerate(head)}
        names = [h[5:] for h in head if h.startswith("deck_")]
        deck = [col["deck_" + n] for n in names]
        hand = [col["opening_hand_" + n] for n in names]
        drawn = [col["drawn_" + n] for n in names]
        i_colors, i_won, i_bucket = col["main_colors"], col["won"], col["user_game_win_rate_bucket"]
        for row in reader:
            colors = row[i_colors]
            if len(colors) not in (2, 3):
                continue
            a = out.get(colors)
            if a is None:
                a = out[colors] = {"games": 0, "wins": 0, "topGames": 0,
                                   "gih": [0] * len(names), "gihWins": [0] * len(names),
                                   "copies": [0] * len(names), "top": [0] * len(names)}
            won = row[i_won] == "True"
            bucket = row[i_bucket]
            top = bucket not in ("", "None") and float(bucket) >= TOP_BUCKET
            a["games"] += 1
            a["wins"] += won
            a["topGames"] += top
            gih, gw, cp, tp = a["gih"], a["gihWins"], a["copies"], a["top"]
            for k in range(len(names)):
                d = row[deck[k]]
                if d in ZERO:
                    continue
                n = int(float(d))
                cp[k] += n
                if top:
                    tp[k] += n
                if row[hand[k]] not in ZERO or row[drawn[k]] not in ZERO:
                    gih[k] += 1
                    gw[k] += won
    result = {"set": code.lower(), "format": fmt, "topBucket": TOP_BUCKET, "archetypes": {}}
    for colors, a in out.items():
        cards = {}
        for k, n in enumerate(names):
            if a["copies"][k]:
                cards[n] = {"gih": a["gih"][k], "gihWins": a["gihWins"][k], "copies": a["copies"][k], "top": a["top"][k]}
        result["archetypes"][colors] = {"games": a["games"], "wins": a["wins"], "topGames": a["topGames"], "cards": cards}
    dest = os.path.join(cache, f"archetypes.{code.lower()}.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return f"{code}: {sum(a['games'] for a in out.values())} two- and three-color games -> {dest}"


def main():
    args = sys.argv[1:]
    fmt, cache = "PremierDraft", CACHE
    if "--format" in args:
        i = args.index("--format"); fmt = args[i + 1]; del args[i:i + 2]
    if "--cache" in args:
        i = args.index("--cache"); cache = args[i + 1]; del args[i:i + 2]
    if not args:
        print(__doc__)
        return 1
    with Pool(len(args)) as pool:
        for line in pool.imap_unordered(summarize, [(c, fmt, cache) for c in args]):
            print(line, flush=True)


if __name__ == "__main__":
    sys.exit(main())
