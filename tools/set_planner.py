#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which card set to implement next: for every paper set, how many of its cards the engine already runs, how many need
only a script, and which missing mechanics block the rest; and, for each candidate set, how many cards of OTHER sets
its new mechanics would unblock. See docs/set-planning.md.

usage: tools/set_planner.py <cards.jsonl.gz> <dump dir from SupportDump> [--sets N] [--detail SET]"""
import argparse, collections, gzip, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SET_TYPES = {"expansion", "core", "draft_innovation", "commander", "masters"}
EXCLUDED = {"plst"}  # reprint lists, not sets
# Ability words have no rules meaning of their own (rule 207.2c): a card with one needs a script, not a new mechanic.
ABILITY_WORDS = {w.lower() for w in """Adamant Addendum Alliance Battalion Bloodrush Celebration Channel Chroma Cohort Constellation
Converge Corrupted Council's dilemma Coven Delirium Descend Domain Eerie Enrage Fateful hour Ferocious Formidable Grandeur
Hellbent Heroic Imprint Inspired Join forces Kinship Landfall Lieutenant Magecraft Metalcraft Morbid Pack tactics Paradox
Parley Radiance Raid Rally Revolt Spell mastery Strive Sweep Tempting offer Threshold Undergrowth Valiant Will of the council
Secret council Survival Void Max speed Start your engines!""".replace("\n", " ").split(" ") if w} | {
    "council's dilemma", "fateful hour", "join forces", "pack tactics", "spell mastery", "tempting offer",
    "will of the council", "secret council", "max speed", "start your engines!"}

set_types = {}

def load(cards_path, dump):
    support = dict(l.rstrip("\n").split("\t") for l in open(os.path.join(dump, "support.tsv")))
    known = {l.strip().lower() for l in open(os.path.join(dump, "keywords.txt")) if l.strip()}
    known |= {l.strip().lower() for l in open(os.path.join(HERE, "engine-mechanics.txt")) if l.strip() and not l.startswith("#")}
    sets = collections.defaultdict(dict)  # code -> name -> missing mechanics
    names = {}
    global set_types
    for line in gzip.open(cards_path, "rt"):
        c = json.loads(line)
        if support.get(c["name"]) == "Full":
            missing = None  # runs already
        else:
            missing = frozenset(k for k in c.get("keywords", []) if k.lower() not in known and k.lower() not in ABILITY_WORDS)
        for p in c.get("printings", []):
            if p.get("set_type") in SET_TYPES:
                sets[p["set"]][c["name"]] = missing
                names[p["set"]] = (p["set_name"], p.get("released_at", ""))
                set_types[p["set"]] = p.get("set_type")
    return sets, names

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cards"); ap.add_argument("dump")
    ap.add_argument("--sets", type=int, default=25, help="how many candidates to list")
    ap.add_argument("--min-cards", type=int, default=150, help="ignore smaller sets as candidates")
    ap.add_argument("--detail", help="show one set's missing mechanics")
    ap.add_argument("--mechanics", action="store_true", help="rank missing mechanics instead of sets")
    ap.add_argument("--types", default="expansion,core,draft_innovation,commander,masters", help="set types considered as candidates")
    ap.add_argument("--sort", choices=["unblocks", "efficiency"], default="efficiency")
    a = ap.parse_args()
    sets, names = load(a.cards, a.dump)
    # Every unsupported card once, with its blockers, and the sets it's in.
    blockers = {}
    in_sets = collections.defaultdict(set)
    for code, cards in sets.items():
        for n, m in cards.items():
            if m is not None: blockers[n] = m; in_sets[n].add(code)

    if a.mechanics:
        # Cards a single mechanic would unblock on its own (it is their only blocker), and every card using it.
        alone = collections.Counter(next(iter(m)) for m in blockers.values() if len(m) == 1)
        total = collections.Counter(k for m in blockers.values() for k in m)
        spread = collections.Counter(k for code, cards in sets.items() for k in {k for m in cards.values() if m for k in m})
        print("mechanic | cards it alone unblocks | cards using it | sets using it")
        for k, n in sorted(total.items(), key=lambda kv: -alone[kv[0]])[:a.sets]:
            print(f"{k} | {alone[k]} | {n} | {spread[k]}")
        return

    if a.detail:
        cards = sets[a.detail]
        mech = collections.Counter(k for m in cards.values() if m for k in m)
        print(f"{a.detail} {names[a.detail][0]}: {len(cards)} cards, {sum(m is None for m in cards.values())} run, "
              f"{sum(m == frozenset() for m in cards.values())} need only a script, {sum(bool(m) for m in cards.values())} blocked")
        for k, n in mech.most_common(): print(f"  {k}: {n}")
        return

    rows = []
    for code, cards in sets.items():
        if len(cards) < a.min_cards or code in EXCLUDED or set_types.get(code) not in a.types.split(","): continue
        new = {k for m in cards.values() if m for k in m}
        # Cards elsewhere whose every missing mechanic this set brings: they'd need only a script afterwards.
        unlocked = [n for n, m in blockers.items() if m and m <= new and code not in in_sets[n]]
        per_set = collections.Counter(s for n in unlocked for s in in_sets[n] if s != code)
        rows.append((len(unlocked), code, len(cards), sum(m is None for m in cards.values()), sum(m == frozenset() for m in cards.values()),
                     sum(bool(m) for m in cards.values()), new, per_set))
    rows.sort(key=lambda r: -(r[0] / max(1, len(r[6])) if a.sort == "efficiency" else r[0]))
    print("unblocks | per mechanic | set | cards | run | script only | blocked | new mechanics | sets helped most")
    for unl, code, total, run, script, blocked, new, per_set in rows[:a.sets]:
        helped = ", ".join(f"{s}:{n}" for s, n in per_set.most_common(5))
        print(f"{unl:7} | {unl / max(1, len(new)):6.0f} | {code} {names[code][0]} ({names[code][1][:4]}) | {total} | {run} | {script} | {blocked} | "
              f"{len(new)}: {', '.join(sorted(new))[:120]} | {helped}")

if __name__ == "__main__":
    main()
