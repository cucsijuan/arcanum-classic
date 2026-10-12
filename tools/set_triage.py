#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepares a set's script work: reuses existing scripts where the rules text is already implemented, and lists the rest
grouped by what blocks them, each rules line pointing at a script that already implements the same line.

usage: tools/set_triage.py <cards.jsonl.gz> <dump dir from SupportDump> <set code> [--out triage.md] [--write]

- Same text: a card whose whole rules text (its own name read as "~") equals a hand-written script's card gets a copy of
  that script under its own name.
- Same abilities: a permanent whose every rules line is either one of its keywords or the "text" of an ability in another
  script gets those abilities, in rules-text order. Only taken from scripts made of abilities alone (no card-wide
  properties that might belong to the line).
- Everything else goes to the report, grouped by the first reason SupportDump's why.tsv gives, with a reference script
  for every line that already appears in one.

Without --write nothing is written to scripts/. Rerun SupportDump afterwards: a written script that still isn't fully
supported shows up in why.tsv. See docs/set-workflow.md."""
import argparse, collections, gzip, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
CARD_WIDE_OK = {"name", "abilities", "generated"}


def load_script(path):
    with open(path, encoding="utf-8") as f:
        text = "\n".join(l for l in f.read().splitlines() if not l.lstrip().startswith("//"))
    return json.loads(text)


def short_name(name):
    return name.split(",")[0] if "," in name else None


def normalize(text, name):
    """Rules text with reminder text dropped and the card's own name as "~"."""
    text = re.sub(r" ?\([^)]*\)", "", text or "")
    for n in filter(None, [name, short_name(name)]):
        text = text.replace(n, "~")
    return re.sub(r"[ \t]+", " ", text).strip()


def renamed(node, old, new):
    """A copy of a script piece with the card's name (and its short name) changed to another card's."""
    text = json.dumps(node, ensure_ascii=False)
    for o, n in ((old, new), (short_name(old), short_name(new) or new)):
        if o: text = text.replace(o, n)
    return json.loads(text)


NUMBER_WORDS = r"\b(a|an|one|two|three|four|five|six|seven|eight|nine|ten|X)\b"


def shape(line):
    """A line with its numbers, number words, mana symbols and subtypes in "Creature — X" lines blurred: same wording, other values."""
    line = re.sub(r"\{[^}]+\}", "{M}", line)
    line = re.sub(r"[+-]?\b\d+\b", "N", line)
    return re.sub(NUMBER_WORDS, "N", line, flags=re.IGNORECASE)


def lines(text):
    return [l.strip() for l in text.split("\n") if l.strip()]


def keyword_line(line, keywords):
    """A line made only of the card's keywords ("Flying, vigilance", "Ward {2}"): the card data gives them."""
    if line.endswith(".") or " — " in line: return False  # a sentence, or an ability word's rules
    parts = [p.strip().lower() for p in line.split(",")]
    return all(any(p == k.lower() or p.startswith(k.lower() + " ") for k in keywords) for p in parts)


def main_types(type_line):
    return frozenset(t for t in ("Creature", "Artifact", "Enchantment", "Land", "Planeswalker", "Instant", "Sorcery", "Battle")
                     if t in type_line.split("—")[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cards"); ap.add_argument("dump"); ap.add_argument("set")
    ap.add_argument("--out", default="triage.md")
    ap.add_argument("--write", action="store_true", help="write the reused and composed scripts into scripts/")
    a = ap.parse_args()

    support = dict(l.rstrip("\n").split("\t", 1) for l in open(os.path.join(a.dump, "support.tsv"), encoding="utf-8"))
    why = collections.defaultdict(list)
    for l in open(os.path.join(a.dump, "why.tsv"), encoding="utf-8"):
        name, reason = l.rstrip("\n").split("\t", 1)
        why[name].append(reason)

    cards, by_id = [], {}
    with gzip.open(a.cards, "rt", encoding="utf-8") as f:
        for l in f:
            c = json.loads(l)
            if c.get("layout") == "token" or "Token" in c.get("type_line", ""): continue
            by_id[c["oracle_id"]] = c
            if any(p.get("set") == a.set for p in c.get("printings", [])): cards.append(c)

    # What the module already implements: whole texts (hand-written scripts) and single abilities by their text.
    whole, ability_of = {}, {}
    for file in sorted(os.listdir(SCRIPTS)):
        oid = file[:-5]
        card = by_id.get(oid)
        if card is None or "card_faces" in card: continue
        try: script = load_script(os.path.join(SCRIPTS, file))
        except (ValueError, OSError): continue
        if support.get(card["name"]) != "Full": continue
        text = normalize(card.get("oracle_text", ""), card["name"])
        if not script.get("generated"):
            whole.setdefault((text, main_types(card["type_line"])), (oid, card["name"], script))
        if set(script) <= CARD_WIDE_OK:
            for ab in script.get("abilities", []):
                ability_of.setdefault(normalize(ab.get("text", ""), card["name"]), (oid, card["name"], ab))
    line_ref = {}  # any scripted line -> a card whose script has it (for the report)
    for (text, _), (oid, name, _) in whole.items():
        for line in lines(text): line_ref.setdefault(line, (oid, name))
    for line, (oid, name, _) in ability_of.items(): line_ref.setdefault(line, (oid, name))
    shape_ref = {}
    for line, ref in line_ref.items(): shape_ref.setdefault(shape(line), ref)

    reused, composed, todo = [], [], []
    for c in sorted(cards, key=lambda c: c["name"]):
        if support.get(c["name"]) == "Full": continue
        path = os.path.join(SCRIPTS, c["oracle_id"] + ".json")
        if os.path.exists(path) and not load_script(path).get("generated"):
            todo.append(c); continue  # hand-written but incomplete: a person finishes it
        text = normalize(c.get("oracle_text", ""), c["name"])
        if "card_faces" not in c and (text, main_types(c["type_line"])) in whole:
            oid, name, script = whole[(text, main_types(c["type_line"]))]
            copy = renamed(script, name, c["name"])
            reused.append((c, name, copy)); continue
        own = [l for l in lines(text) if not keyword_line(l, c.get("keywords", []))]
        if ("card_faces" not in c and own and not main_types(c["type_line"]) & {"Instant", "Sorcery"}
                and all(l in ability_of for l in own)):
            abilities = [renamed(ability_of[l][2], ability_of[l][1], c["name"]) for l in own]
            composed.append((c, sorted({ability_of[l][1] for l in own}), {"name": c["name"], "abilities": abilities})); continue
        todo.append(c)

    if a.write:
        for c, _, script in reused + composed:
            with open(os.path.join(SCRIPTS, c["oracle_id"] + ".json"), "w", encoding="utf-8") as out:
                json.dump(script, out, indent=2, ensure_ascii=False); out.write("\n")

    def reasons(c):
        names = [c["name"]] + [f["name"] for f in c.get("card_faces", [])]
        return [next((r[len(n) + 2:] for n in names if r.startswith(n + ": ")), r) for r in why.get(c["name"], [])]

    def new_lines(c):
        return sum(1 for face in c.get("card_faces") or [c] for l in lines(normalize(face.get("oracle_text", ""), c["name"]))
                   if not keyword_line(l, c.get("keywords", [])) and l not in line_ref)

    # Blocked by something besides the script (a keyword, a layout...): grouped by that; the rest, fewest new lines first.
    groups = collections.defaultdict(list)
    for c in todo:
        blockers = [r for r in reasons(c) if r != "needs a script"]
        groups[re.sub(r"\b\d+\b", "N", blockers[0]) if blockers else ""].append(c)
    full = sum(support.get(c["name"]) == "Full" for c in cards)
    with open(a.out, "w", encoding="utf-8") as out:
        w = lambda s="": out.write(s + "\n")
        w(f"# {a.set}: {len(cards)} cards, {full} run, {len(reused)} same text, {len(composed)} same abilities, {len(todo)} to do")
        w(); w("Each rules line: `=` a script has this line, `≈` a script has it with other numbers or mana (file in scripts/), "
              "`+` one of its keywords, `·` new.")
        w(); w(f"## Same text as a scripted card ({len(reused)}{'' if a.write else ', not written'})")
        for c, src, _ in reused: w(f"- {c['name']} ← {src}")
        w(); w(f"## Same abilities as scripted cards ({len(composed)}{'' if a.write else ', not written'})")
        for c, srcs, _ in composed: w(f"- {c['name']} ← {', '.join(srcs)}")
        for reason, group in sorted(groups.items(), key=lambda kv: (kv[0] == "", -len(kv[1]))):
            w(); w(f"## {reason or 'Script only, fewest new lines first'} ({len(group)})")
            for c in sorted(group, key=lambda c: (new_lines(c), c["name"])):
                w(); w(f"### {c['name']} — {c.get('mana_cost', '')} {c['type_line']} `{c['oracle_id']}`")
                if len(reasons(c)) > 1: w("why: " + "; ".join(reasons(c)))
                faces = c.get("card_faces") or [c]
                for face in faces:
                    if len(faces) > 1: w(f"*{face['name']}* — {face.get('type_line', '')}")
                    for line in lines(normalize(face.get("oracle_text", ""), c["name"])):
                        if keyword_line(line, c.get("keywords", [])): w(f"- `+` {line}")
                        elif line in line_ref: w(f"- `=` {line} → {line_ref[line][0]}.json ({line_ref[line][1]})")
                        elif shape(line) in shape_ref: w(f"- `≈` {line} → {shape_ref[shape(line)][0]}.json ({shape_ref[shape(line)][1]})")
                        else: w(f"- `·` {line}")
    print(f"{a.set}: {len(cards)} cards, {full} run, {len(reused)} same text, {len(composed)} same abilities, {len(todo)} to do"
          f" → {a.out}{'' if a.write else ' (nothing written: --write)'}")


if __name__ == "__main__":
    main()
