#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds a set's draft ratings from the 17Lands public datasets (CC BY 4.0, https://www.17lands.com/public_datasets).

Usage: tools/draft_ratings.py <set code> [format] [--cache <dir>]

Downloads the set's game data and draft data (format default: PremierDraft) into the cache folder (default:
~/.cache/arcanum/17lands), then writes ratings/<set>.json:
- gih: the win rate of the games where the card was in hand (in the opening hand or drawn), and games: how many;
- ata: the pick it was taken at on average (1 = first pick of a pack), and picks: how many times it was taken;
- mean / sd: the average and spread of gih over the cards with at least MIN_GAMES games (for grades).
The game reads the file for the computer players' picks and, in career drafts, to show the ratings.
17Lands asks not to query its site's API automatically: only the public datasets are used.
"""
import csv
import gzip
import json
import math
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
URL = "https://17lands-public.s3.amazonaws.com/analysis_data/{kind}_data/{kind}_data_public.{set}.{format}.csv.gz"
CREDIT = "Card ratings: 17Lands public data (CC BY 4.0), 17lands.com/public_datasets"
MIN_GAMES = 500

csv.field_size_limit(sys.maxsize)


def download(kind, code, fmt, cache):
    path = os.path.join(cache, f"{kind}_data_public.{code}.{fmt}.csv.gz")
    if not os.path.exists(path):
        url = URL.format(kind=kind, set=code, format=fmt)
        print(f"Downloading {url}", file=sys.stderr)
        os.makedirs(cache, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "arcanum-classic draft_ratings"})
        with urllib.request.urlopen(request) as response, open(path + ".part", "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        os.replace(path + ".part", path)
    return path


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        yield header
        yield from reader


def in_hand(path):
    """Per card: games in hand and games won with it in hand."""
    it = rows(path)
    header = next(it)
    won = header.index("won")
    cards = {}
    for i, col in enumerate(header):
        for prefix in ("opening_hand_", "drawn_"):
            if col.startswith(prefix):
                cards.setdefault(col[len(prefix):], []).append(i)
    games = {name: 0 for name in cards}
    wins = {name: 0 for name in cards}
    total = 0
    for n, row in enumerate(it):
        w = row[won] == "True"
        total += 1
        for name, cols in cards.items():
            if any(row[c] not in ("0", "") for c in cols):
                games[name] += 1
                if w:
                    wins[name] += 1
        if n % 100000 == 0 and n:
            print(f"  {n} games", file=sys.stderr)
    return games, wins, total


def taken_at(path):
    """Per card: how many times it was picked and the sum of the pick numbers (from 1)."""
    it = rows(path)
    header = next(it)
    pick, number = header.index("pick"), header.index("pick_number")
    count, total = {}, {}
    for n, row in enumerate(it):
        name = row[pick]
        if not name:
            continue
        count[name] = count.get(name, 0) + 1
        total[name] = total.get(name, 0) + int(row[number]) + 1
        if n % 1000000 == 0 and n:
            print(f"  {n} picks", file=sys.stderr)
    return count, total


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    cache = os.path.expanduser("~/.cache/arcanum/17lands")
    if "--cache" in argv:
        cache = argv[argv.index("--cache") + 1]
        args.remove(cache)
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    code = args[0].upper()
    fmt = args[1] if len(args) > 1 else "PremierDraft"

    games, wins, total = in_hand(download("game", code, fmt, cache))
    picks, pick_sum = taken_at(download("draft", code, fmt, cache))

    rated = [wins[n] / games[n] for n in games if games[n] >= MIN_GAMES]
    mean = sum(rated) / len(rated) if rated else 0.5
    sd = math.sqrt(sum((r - mean) ** 2 for r in rated) / len(rated)) if rated else 0.03

    cards = {}
    for name in sorted(set(games) | set(picks)):
        entry = {}
        if games.get(name):
            entry["gih"] = round(wins[name] / games[name], 4)
            entry["games"] = games[name]
        if picks.get(name):
            entry["ata"] = round(pick_sum[name] / picks[name], 2)
            entry["picks"] = picks[name]
        if entry:
            cards[name] = entry

    out = {
        "credit": CREDIT,
        "set": code.lower(),
        "format": fmt,
        "games": total,
        "mean": round(mean, 4),
        "sd": round(sd, 4),
        "cards": cards,
    }
    os.makedirs(os.path.join(ROOT, "ratings"), exist_ok=True)
    path = os.path.join(ROOT, "ratings", code.lower() + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{path}: {len(cards)} cards from {total} games (in hand: mean {mean:.1%}, sd {sd:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
