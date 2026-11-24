#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds a 60-card deck for each archetype of a set, from how the set's cards did in that archetype.

Usage: tools/build_archetype_decks.py <card-file.jsonl.gz> <support.tsv> <set code> [--stats <archetypes.json>]
       [--ratings <ratings.json> --archetypes WU,UB,... --source <text>] [--min-share 0.03] [--dry-run]

Data, one of:
- --stats (default ~/.cache/arcanum/17lands/archetypes.<set>.json, made by tools/archetype_stats.py from the 17Lands
  public game data): the archetypes are the color combinations played in at least --min-share of the set's two- and
  three-color games. A card's score is its win rate in that archetype's games where it was in hand (shrunk toward the
  archetype's win rate when it has few games); only cards the stronger players put in that archetype's decks are used,
  and the deck's curve, creature count and land count follow those decks.
- --ratings: a JSON object card name -> rating (any scale, higher is better) for sets without game data, with
  --archetypes naming the color combinations and --source naming where the ratings come from; the curve and creature count then follow DEFAULT_CURVE.
Only cards the engine fully supports (support.tsv from tools/SupportDump) with a printing in the set are used; every line
names that printing. Sweepers stay out of creature decks. Nonland cards get four copies (two for legendary ones), the strongest first, as the curve allows;
the set's lands that make two of the archetype's colors get four copies when the stronger players play them. Basic lands
split by the colored mana symbols of the spells. Writes decks/<set>-<colors>.txt (colors lowercase, in WUBRG order).
"""
import gzip
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

CACHE = os.path.expanduser("~/.cache/arcanum/17lands")
BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
COLOR_NAMES = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
ORDER = "WUBRG"
SHRINK = 300            # games of prior weight toward the archetype's win rate
MIN_PRESENCE = 0.04     # copies per stronger player's game for a card to count as part of the archetype
DEFAULT_CURVE = {1: 0.08, 2: 0.30, 3: 0.24, 4: 0.20, 5: 0.12, 6: 0.06}
DEFAULT_CREATURES = 0.62
# A sweeper that hits its own side's creatures stays out of decks with this share of creatures among the spells.
WIPE = re.compile(r"(destroy|exile) all (other )?(nonland permanents|creatures)|all creatures get -|deals \d+ damage to each creature", re.I)
WIPE_CREATURES = 0.45
CREATURE_SLACK = 4      # copies the creatures may run over the stronger players' share
CURVE_SLACK = 2         # copies a mana value bucket may run over its share
# Synergy. A card's lift is how often the stronger players put it in this archetype's decks over how often they put it in
# the other two-color archetypes that share a color with it and can cast it: a card the archetype's drafters take more
# than their neighbors do belongs to its plan. The score gains SYNERGY * ln(lift) (lift held between 1/4 and 4), and a
# card played well under its neighbors' rate (lift below MIN_LIFT) stays out. A card only this archetype can cast counts
# as GOLD_LIFT.
SYNERGY = 0.04
MIN_LIFT = 0.6
GOLD_LIFT = 3.0
# A creature type is the archetype's tribe when its creatures make at least TRIBE_COPIES copies of the stronger players'
# decks and TRIBE_LIFT times their neighbors'; its cards, and cards that name it, gain TRIBE_BONUS.
TRIBE_COPIES = 2.0
TRIBE_LIFT = 1.5
TRIBE_BONUS = 0.03
# --themes: for sets without game data, a JSON object archetype -> {"text": regex, "types": [creature types]}, from the
# set's archetype signposts; cards matching it gain THEME_BONUS. Ratings are moved to the game data's scale (RATING_LOW..RATING_HIGH) so the bonuses weigh the same.
THEME_BONUS = 0.03
RATING_LOW, RATING_HIGH = 0.45, 0.60


def set_printings(path, code):
    """name -> collector number of the card's printing in the set (the booster one, lowest number first)."""
    opener = gzip.open if path.endswith(".gz") else open
    found = {}
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if f'"set":"{code}"' not in line.replace(" ", ""):
                continue
            c = json.loads(line)
            # A printings source has one printing per line; Arcanum's own card file lists each card's printings.
            for p in c.get("printings", [c]):
                if p.get("set") != code or p.get("lang", "en") != "en":
                    continue
                digits = "".join(ch for ch in p["collector_number"] if ch.isdigit())
                rank = (not p.get("booster", False), int(digits) if digits else 10**9)
                if c["name"] not in found or rank < found[c["name"]][0]:
                    found[c["name"]] = (rank, p["collector_number"])
    return {name: number for name, (_, number) in found.items()}


def canonical(colors):
    return "".join(c for c in ORDER if c in colors.upper())


def mana_value(card):
    """The front face's mana value, from its cost (the card file has no mana value field)."""
    cost = card.get("mana_cost", "").split(" // ")[0]
    total = 0
    for sym in re.findall(r"\{([^}]*)\}", cost):
        if sym.isdigit():
            total += int(sym)
        elif sym not in ("X", "Y", "Z"):
            total += 1
    return total


def bucket(card):
    return max(1, min(6, mana_value(card)))


def front(name):
    return name.split(" // ")[0]


def load_cards(path):
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            out.setdefault(c["name"], c)
            out.setdefault(front(c["name"]), c)
    return out


def subtypes(card):
    line = card.get("type_line", "").split(" // ")[0]
    if "Creature" not in line or "—" not in line:
        return set()
    return set(line.split("—")[1].split())


def names_type(card, types):
    text = card.get("oracle_text", "")
    return any(re.search(rf"\b{t}s?\b", text) for t in types)


def lifts(stats, cards, arch):
    """name -> lift of each card of the archetype (see SYNERGY), and the archetype's tribes."""
    def presence(a, name):
        s = stats[a]["cards"].get(name)
        return s["top"] / max(1, stats[a]["topGames"]) if s else 0.0
    neighbors = [b for b in stats if b != arch and len(b) == 2 and set(b) & set(arch)]
    out = {}
    type_here, type_there = {}, {}
    for name in stats[arch]["cards"]:
        c = cards.get(name)
        if c is None:
            continue
        identity = set(c.get("color_identity", []))
        here = presence(arch, name)
        there = [v for v in (presence(b, name) for b in neighbors if identity <= set(b)) if v > 0.01]
        if there:
            out[name] = here / (sum(there) / len(there))
        else:
            out[name] = GOLD_LIFT if len(identity) >= 2 else 1.0
        for t in subtypes(c):
            type_here[t] = type_here.get(t, 0) + here
            type_there[t] = type_there.get(t, 0) + (sum(there) / len(there) if there else 0)
    tribes = {t for t, v in type_here.items() if v >= TRIBE_COPIES and v >= TRIBE_LIFT * type_there.get(t, 0)}
    return out, tribes


def load_support(path):
    full = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > 1 and parts[1] == "Full":
                full.add(parts[0])
    return full


def pips(card):
    cost = card.get("mana_cost", "")
    return {c: len(re.findall(r"\{[^}]*" + c + r"[^}]*\}", cost)) for c in ORDER}


def makes(card):
    """The colors a land taps for, from its rules text."""
    text = card.get("oracle_text", "")
    out = set()
    for sym in re.findall(r"Add ([^.]*)", text):
        out |= set(re.findall(r"\{([WUBRG])\}", sym))
    return out


def build(colors, scored, cards, curve, creature_share, nonland, lands_in):
    """scored: [(score, name)] best first. Returns [(count, name)] for the spells and the lands."""
    targets = {b: curve.get(b, 0) * nonland for b in range(1, 7)}
    used = {b: 0 for b in range(1, 7)}
    creatures_target = round(creature_share * nonland)
    picks, total, creatures = [], 0, 0
    for _, name in scored:
        if total >= nonland:
            break
        c = cards[name]
        is_creature = "Creature" in c["type_line"]
        n = 2 if "Legendary" in c["type_line"] else 4
        n = min(n, nonland - total)
        b = bucket(c)
        if used[b] + n > targets[b] + CURVE_SLACK:
            continue
        left = nonland - total
        if not is_creature and creatures_target - creatures >= left:
            continue
        if is_creature and creatures + n > creatures_target + CREATURE_SLACK:
            continue
        picks.append((n, name))
        total += n
        used[b] += n
        creatures += n if is_creature else 0
    # A curve that ran out of good cards: fill from the best left, any mana value.
    for _, name in scored:
        if total >= nonland:
            break
        if any(p[1] == name for p in picks):
            continue
        n = min(2 if "Legendary" in cards[name]["type_line"] else 4, nonland - total)
        picks.append((n, name))
        total += n
    return picks


def main():
    args = sys.argv[1:]
    opts = {}
    for key in ("--stats", "--ratings", "--archetypes", "--min-share", "--source", "--themes"):
        if key in args:
            i = args.index(key)
            opts[key] = args[i + 1]
            del args[i:i + 2]
    dry = "--dry-run" in args
    if dry:
        args.remove("--dry-run")
    if len(args) != 3:
        print(__doc__)
        return 1
    card_file, support_file, code = args
    code = code.lower()
    with open(os.path.join(ROOT, "sets", f"{code}.json"), encoding="utf-8") as f:
        set_info = json.load(f)
    in_set = set(set_info["cards"])
    numbers = set_printings(card_file, code)
    cards = load_cards(card_file)
    full = load_support(support_file)

    def usable(name):
        c = cards.get(name)
        return c is not None and front(c["name"]) in full and (c["name"] in numbers or front(c["name"]) in numbers) \
            and (c["name"] in in_set or front(c["name"]) in in_set)

    themes = {}
    if "--themes" in opts:
        with open(opts["--themes"], encoding="utf-8") as f:
            themes = {canonical(k): v for k, v in json.load(f).items() if not k.startswith("_")}

    # (colors, {name: score}, {name: presence}, curve, creature share, nonland count, games, {name: lift}, tribes)
    archetypes = []
    if "--ratings" in opts:
        with open(opts["--ratings"], encoding="utf-8") as f:
            ratings = json.load(f)
        low, high = min(ratings.values()), max(ratings.values())
        scaled = {n: RATING_LOW + (r - low) / ((high - low) or 1) * (RATING_HIGH - RATING_LOW) for n, r in ratings.items()}
        for colors in opts["--archetypes"].split(","):
            archetypes.append((canonical(colors), scaled, None, DEFAULT_CURVE, DEFAULT_CREATURES, 36, None, None, set()))
    else:
        path = opts.get("--stats", os.path.join(CACHE, f"archetypes.{code}.json"))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        stats = data["archetypes"]
        source = data.get("source")
        all_games = sum(a["games"] for a in stats.values())
        share = float(opts.get("--min-share", 0.03))
        for colors, a in sorted(stats.items(), key=lambda kv: -kv[1]["games"]):
            if a["games"] < share * all_games:
                continue
            base = a["wins"] / a["games"]
            top_games = max(1, a["topGames"])
            scores, presence = {}, {}
            curve = {b: 0.0 for b in range(1, 7)}
            creature_copies = spell_copies = land_copies = 0.0
            for name, s in a["cards"].items():
                presence[name] = s["top"] / top_games
                scores[name] = (s["gihWins"] + SHRINK * base) / (s["gih"] + SHRINK)
                c = cards.get(name)
                if c is None:
                    continue
                per_deck = s["top"] / top_games
                if "Land" in c["type_line"]:
                    land_copies += per_deck
                    continue
                spell_copies += per_deck
                curve[bucket(c)] += per_deck
                if "Creature" in c["type_line"]:
                    creature_copies += per_deck
            curve = {b: v / spell_copies for b, v in curve.items()}
            # 24 lands, 23 for a low curve and 25 for a high one (the stronger players' average mana value).
            mean_mv = sum(b * v for b, v in curve.items())
            nonland = 37 if mean_mv < 2.6 else 35 if mean_mv > 3.4 else 36
            lift, tribes = lifts(stats, cards, colors)
            archetypes.append((canonical(colors), scores, presence, curve, creature_copies / spell_copies, nonland,
                               (a["games"], base, land_copies), lift, tribes))

    for colors, scores, presence, curve, creature_share, nonland, info, lift, tribes in archetypes:
        theme = themes.get(colors, {})
        theme_text = re.compile(theme["text"], re.I) if theme.get("text") else None
        theme_types = set(theme.get("types", []))
        allowed = set(colors)
        spells, duals = [], []
        for name, score in scores.items():
            if not usable(name):
                continue
            c = cards[name]
            if presence is not None and presence.get(name, 0) < MIN_PRESENCE:
                continue
            identity = set(c.get("color_identity", []))
            if "Land" in c["type_line"]:
                made = makes(c)
                if "Basic" not in c["type_line"] and len(made & allowed) >= 2 and made <= allowed:
                    duals.append((score, front(c["name"]) if front(c["name"]) in numbers else c["name"]))
                continue
            if not identity <= allowed:
                continue
            if creature_share >= WIPE_CREATURES and WIPE.search(c.get("oracle_text", "")):
                continue
            if lift is not None:
                if lift.get(name, 1.0) < MIN_LIFT:
                    continue
                score += SYNERGY * math.log(max(0.25, min(4.0, lift.get(name, 1.0))))
            if tribes and (subtypes(c) & tribes or names_type(c, tribes)):
                score += TRIBE_BONUS
            if (theme_text and theme_text.search(c.get("oracle_text", "") + " " + c["type_line"])) or \
                    (theme_types and (subtypes(c) & theme_types or names_type(c, theme_types))):
                score += THEME_BONUS
            spells.append((score, name))
        spells.sort(key=lambda x: -x[0])
        duals.sort(key=lambda x: -x[0])
        picks = build(colors, spells, cards, curve, creature_share, nonland, None)
        land_count = 60 - sum(n for n, _ in picks)
        lands = [(4, name) for _, name in duals[:max(0, min(len(duals), (land_count - 8) // 4))]]
        weights = {c: 0 for c in colors}
        for n, name in picks:
            for c, k in pips(cards[name]).items():
                if c in weights:
                    weights[c] += n * k
        basics_left = land_count - sum(n for n, _ in lands)
        total_weight = sum(weights.values()) or 1
        counts = {c: max(1 if weights[c] else 0, round(basics_left * weights[c] / total_weight)) for c in colors}
        while sum(counts.values()) > basics_left:
            counts[max(counts, key=counts.get)] -= 1
        while sum(counts.values()) < basics_left:
            counts[max(weights, key=weights.get)] += 1

        def line(n, name):
            full_name = cards[name]["name"] if name in cards else name
            key = next((k for k in (name, full_name, front(full_name)) if k in numbers), front(full_name))
            if key in numbers:
                return f"{n} {key} ({code.upper()}) {numbers[key]}"
            return f"{n} {key}"
        colors_text = "-".join(COLOR_NAMES[c] for c in colors)
        out = [f"# {code.upper()}: the {colors_text} archetype, 60 cards."]
        if info and source:
            games, base, _ = info
            out.append(f"# Built from {source}: {games} games of {colors} decks, {base:.1%} won; cards by win rate in "
                       f"the deck and by how much more this archetype plays them than its neighbors.")
        elif info:
            games, base, _ = info
            out.append(f"# Built from 17Lands public game data (CC BY 4.0): {games} games of {colors} decks, "
                       f"{base:.1%} won; cards by win rate in hand and by how much more this archetype's stronger "
                       f"players play them than its neighbors', curve and creatures as their decks.")
        else:
            theme_note = f", favoring its theme: {theme['note']}" if theme.get("note") else ""
            out.append(f"# Built from {opts.get('--source', 'card ratings')}: the best rated cards of the archetype's "
                       f"colors{theme_note}.")
        out += [line(n, name) for n, name in sorted(picks, key=lambda p: (mana_value(cards[p[1]]), p[1]))]
        out += [line(n, name) for n, name in lands]
        out += [line(counts[c], BASICS[c]) for c in colors if counts[c]]
        path = os.path.join(ROOT, "decks", f"{code}-{colors.lower()}.txt")
        creatures = sum(n for n, name in picks if "Creature" in cards[name]["type_line"])
        summary = (f"{code}-{colors.lower()}: {sum(n for n, _ in picks)} spells ({creatures} creatures, "
                   f"{len(picks)} different), {land_count} lands ({sum(n for n, _ in lands)} nonbasic) "
                   f"from {len(spells)} candidates")
        if dry:
            print(summary)
            print("\n".join(out[2:]))
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        print(summary, "->", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    sys.exit(main())
