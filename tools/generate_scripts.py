#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Generates card scripts for cards whose rules text follows common, fixed phrasings.

Usage:
    tools/generate_scripts.py <card-file.jsonl[.gz]> [--dry-run] [--report report.txt]

Only cards whose *every* rules-text line is understood get a script; anything partially understood is
skipped. Hand-written scripts (files without "generated": true) are never touched. Generated scripts carry
"generated": true so they can be reviewed and promoted to hand-written later.
"""
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

# Keywords the engine implements (keep in sync with the engine's Keyword enum).
ENGINE_KEYWORDS = {
    "flying", "reach", "vigilance", "haste", "defender", "menace", "trample", "deathtouch", "lifelink",
    "first strike", "double strike", "indestructible", "hexproof", "shroud",
    "equip", "enchant",  # derived from rules text by the engine's card factory
}
# Lines the engine derives from card data on its own.
DERIVED_LINE = re.compile(
    r"^(\{T\}: Add \{[WUBRGC]\}((, | or |, or )\{[WUBRGC]\})*"
    r"|\{T\}: Add one mana of any color"
    r"|Equip (\{[0-9WUBRGC]+\})+"
    r"|Enchant (creature|land|artifact|enchantment|permanent)( you control)?"
    r"|This (land|creature|artifact|permanent) enters tapped)$")

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
SINGLE_FACE = {"normal"}


class Unsupported(Exception):
    pass


def num(word):
    word = word.lower()
    if word.isdigit():
        return int(word)
    if word in NUMBERS:
        return NUMBERS[word]
    raise Unsupported(word)


def target_kind(phrase):
    """'target creature you control' -> 'creature:you'. Returns None if not a target phrase we support."""
    phrase = phrase.strip()
    table = {
        "any target": "any",
        "target creature": "creature",
        "target creature or planeswalker": "creature",
        "target creature you control": "creature:you",
        "target creature you don't control": "creature:opponent",
        "target creature an opponent controls": "creature:opponent",
        "target player": "player",
        "target player or planeswalker": "player",
        "target opponent": "opponent",
        "target opponent or planeswalker": "opponent",
        "target artifact": "artifact",
        "target enchantment": "enchantment",
        "target land": "land",
        "target permanent": "permanent",
        "target spell": "spell",
    }
    return table.get(phrase)


class Builder:
    """Accumulates targets while effects are parsed, so effects can refer to "target", "target2", ..."""

    def __init__(self):
        self.targets = []

    def add_target(self, kind):
        self.targets.append(kind)
        n = len(self.targets)
        return "target" if n == 1 else f"target{n}"


KW = r"(flying|reach|vigilance|haste|trample|deathtouch|lifelink|first strike|double strike|indestructible|hexproof|menace)"


def keywords_list(text):
    """'flying and trample' -> ['Flying', 'Trample']"""
    parts = re.split(r", and |, | and ", text)
    out = []
    for p in parts:
        p = p.strip()
        if p.lower() not in ENGINE_KEYWORDS - {"equip", "enchant"}:
            raise Unsupported(p)
        out.append(p[0].upper() + p[1:])
    return out


def effect(sentence, b):
    """Parses one effect sentence (no trailing period). Returns a list of effect dicts."""
    s = sentence.strip()
    s = re.sub(r"^(Then|then) ", "", s)
    if s and s[0].islower() and not s.startswith(("it ",)):
        s = s[0].upper() + s[1:]
    m = re.fullmatch(r"(?:CARDNAME|This \w+|It|it) deals (\w+) damage to (.+?)(?: and (\w+) damage to that (?:creature|permanent)'s controller)?", s)
    if m:
        kind = target_kind(m.group(2))
        if kind is None:
            if m.group(2) == "each opponent":
                return [{"damage": num(m.group(1)), "to": "opponents"}]
            if m.group(2) == "you":
                return [{"damage": num(m.group(1)), "to": "you"}]
            raise Unsupported(s)
        subj = b.add_target(kind)
        out = [{"damage": num(m.group(1)), "to": subj}]
        if m.group(3):
            out.append({"damage": num(m.group(3)), "to": "targetController"})
        return out
    m = re.fullmatch(r"(?:You )?[Dd]raw (\w+) cards?", s)
    if m:
        return [{"draw": num(m.group(1))}]
    m = re.fullmatch(r"(Target player|Target opponent|Each player|Each opponent) draws (\w+) cards?", s)
    if m:
        who = {"Target player": None, "Target opponent": None, "Each player": "everyone", "Each opponent": "opponents"}[m.group(1)]
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        return [{"draw": num(m.group(2)), "who": who}]
    m = re.fullmatch(r"You gain (\w+) life", s)
    if m:
        return [{"gainLife": num(m.group(1))}]
    m = re.fullmatch(r"(Target player|Target opponent|Each opponent|Each player) (gains|loses) (\w+) life", s)
    if m:
        who = {"Each opponent": "opponents", "Each player": "everyone"}.get(m.group(1))
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        key = "gainLife" if m.group(2) == "gains" else "loseLife"
        return [{key: num(m.group(3)), "who": who}]
    m = re.fullmatch(r"You lose (\w+) life", s)
    if m:
        return [{"loseLife": num(m.group(1))}]
    m = re.fullmatch(r"(Destroy|Exile|Tap|Untap) (target .+)", s)
    if m:
        kind = target_kind(m.group(2))
        if kind is None or kind in ("any", "player", "opponent", "spell"):
            raise Unsupported(s)
        key = {"Destroy": "destroy", "Exile": "exile", "Tap": "tap", "Untap": "untap"}[m.group(1)]
        return [{key: b.add_target(kind)}]
    m = re.fullmatch(r"Return (target .+?) to its owner's hand", s)
    if m:
        kind = target_kind(m.group(1))
        if kind is None or kind in ("any", "player", "opponent", "spell"):
            raise Unsupported(s)
        return [{"bounce": b.add_target(kind)}]
    if s == "Counter target spell":
        return [{"counter": b.add_target("spell")}]
    m = re.fullmatch(r"(Target player|Target opponent|Each opponent|You) mills? (\w+) cards?", s)
    if m:
        who = {"Each opponent": "opponents", "You": "you"}.get(m.group(1))
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        return [{"mill": num(m.group(2)), "who": who}]
    m = re.fullmatch(r"(Target creature(?: you control)?|This creature|CARDNAME|It|it) gets ([+-]\d+)/([+-]\d+)(?: and gains " + KW + r"(?: and " + KW + r")?)? until end of turn", s)
    if m:
        what = m.group(1)
        if what.startswith("Target"):
            subj = b.add_target("creature:you" if "you control" in what else "creature")
        else:
            subj = "self"
        out = {"pump": [int(m.group(2)), int(m.group(3))], "what": subj}
        kws = [k for k in (m.group(4), m.group(5)) if k]
        if kws:
            out["keywords"] = keywords_list(" and ".join(kws))
        return [out]
    m = re.fullmatch(r"(Target creature(?: you control)?|This creature|CARDNAME) gains (.+) until end of turn", s)
    if m:
        subj = "self" if not m.group(1).startswith("Target") else b.add_target("creature:you" if "you control" in m.group(1) else "creature")
        return [{"pump": [0, 0], "what": subj, "keywords": keywords_list(m.group(2))}]
    m = re.fullmatch(r"Put (\w+) \+1/\+1 counters? on (target creature(?: you control)?|this creature|CARDNAME)", s)
    if m:
        what = m.group(2)
        subj = "self" if not what.startswith("target") else b.add_target("creature:you" if "you control" in what else "creature")
        return [{"counters": num(m.group(1)), "what": subj}]
    m = re.fullmatch(r"Create (\w+) (\d+)/(\d+) ((?:white|blue|black|red|green|colorless)(?: and (?:white|blue|black|red|green))?) ([A-Z][a-z]+(?: [A-Z][a-z]+)*) (?:artifact )?creature tokens?(?: with (.+))?", s)
    if m:
        token = {"name": m.group(5), "types": "Creature — " + m.group(5), "power": int(m.group(2)), "toughness": int(m.group(3))}
        letters = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
        colors = [letters[w] for w in m.group(4).split(" and ") if w in letters]
        if colors:
            token["colors"] = colors
        if m.group(6):
            token["keywords"] = keywords_list(m.group(6))
        return [{"tokens": num(m.group(1)), "token": token}]
    raise Unsupported(s)


def effects_of(text, b):
    """Splits '<sentence>. <sentence>' and parses each sentence."""
    out = []
    for sentence in [x for x in re.split(r"\.\s*", text) if x.strip()]:
        out.extend(effect(sentence, b))
    return out


TRIGGERS = [
    (r"When (?:this creature|CARDNAME) enters, (.+)", "enters"),
    (r"When (?:this creature|CARDNAME) dies, (.+)", "dies"),
    (r"Whenever (?:this creature|CARDNAME) attacks, (.+)", "attacks"),
    (r"At the beginning of your upkeep, (.+)", "upkeep"),
    (r"At the beginning of your end step, (.+)", "endStep"),
    (r"Whenever (?:this creature|CARDNAME) deals combat damage to a player, (.+)", "combatDamageToPlayer"),
]


def parse_cost(cost):
    parts = []
    for raw in [c.strip() for c in cost.split(",")]:
        if raw == "{T}":
            parts.append("{T}")
        elif re.fullmatch(r"Sacrifice (this creature|this artifact|this enchantment|CARDNAME)", raw):
            parts.append("sacrifice")
        elif re.fullmatch(r"(\{[0-9WUBRGC]+\})+", raw):
            parts.append(raw)
        else:
            raise Unsupported(raw)
    return ", ".join(parts)


def static(line):
    if line in ("This creature can't block", "CARDNAME can't block"):
        return {"affects": "self", "pump": [0, 0], "keywords": ["Can't block"]}
    if line in ("This creature can't be blocked", "CARDNAME can't be blocked"):
        return {"affects": "self", "pump": [0, 0], "keywords": ["Can't be blocked"]}
    m = re.fullmatch(r"(Other )?(?:([A-Z][a-z]+) )?[Cc]reatures you control get ([+-]\d+)/([+-]\d+)(?: and have (.+))?", line)
    if m:
        st = {"affects": "creatures:you", "pump": [int(m.group(3)), int(m.group(4))]}
        if m.group(1):
            st["other"] = True
        if m.group(2):
            st["subtype"] = m.group(2)
        if m.group(5):
            st["keywords"] = keywords_list(m.group(5))
        return st
    m = re.fullmatch(r"Creatures your opponents control get ([+-]\d+)/([+-]\d+)", line)
    if m:
        return {"affects": "creatures:opponents", "pump": [int(m.group(1)), int(m.group(2))]}
    m = re.fullmatch(r"(Enchanted|Equipped) creature gets ([+-]\d+)/([+-]\d+)(?: and has (.+))?", line)
    if m:
        st = {"affects": m.group(1).lower(), "pump": [int(m.group(2)), int(m.group(3))]}
        if m.group(4):
            st["keywords"] = keywords_list(m.group(4))
        return st
    m = re.fullmatch(r"(Enchanted|Equipped) creature has (.+)", line)
    if m:
        return {"affects": m.group(1).lower(), "pump": [0, 0], "keywords": keywords_list(m.group(2))}
    return None


def is_keyword_line(line, keywords):
    parts = [p.strip().lower() for p in line.split(",")]
    kws = {k.lower() for k in keywords}
    return all(p in kws for p in parts)


def generate(card):
    if card.get("layout") not in SINGLE_FACE:
        raise Unsupported("layout")
    if any(k.lower() not in ENGINE_KEYWORDS for k in card.get("keywords", [])):
        raise Unsupported("keyword")
    for stat in ("power", "toughness"):
        if stat in card and not re.fullmatch(r"-?\d+", card[stat]):
            raise Unsupported("stat")
    if re.search(r"\{X\}|/[WUBRGP]\}", card.get("mana_cost", "")):
        raise Unsupported("cost")

    name = card["name"]
    text = re.sub(r"\s*\([^)]*\)", "", card.get("oracle_text", ""))
    text = text.replace(name, "CARDNAME")
    types = card.get("type_line", "")
    is_spell = "Instant" in types or "Sorcery" in types
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    script = {}
    abilities = []
    spell_text = []
    for line in lines:
        bare = line.rstrip(".")
        if DERIVED_LINE.fullmatch(bare) or is_keyword_line(bare, card.get("keywords", [])):
            continue
        if is_spell:
            spell_text.append(line)
            continue
        m = re.fullmatch(r"(?:This creature|CARDNAME) enters with (\w+) \+1/\+1 counters? on it\.?", line)
        if m:
            script["entersWithCounters"] = num(m.group(1))
            continue
        st = static(bare)
        if st is not None:
            abilities.append({"static": st, "text": line.replace("CARDNAME", name)})
            continue
        handled = False
        for pattern, trigger in TRIGGERS:
            m = re.fullmatch(pattern, line)
            if m:
                b = Builder()
                effs = effects_of(m.group(1), b)
                ab = {"trigger": trigger}
                if b.targets:
                    ab["targets"] = b.targets
                ab["effects"] = effs
                ab["text"] = line.replace("CARDNAME", name)
                abilities.append(ab)
                handled = True
                break
        if handled:
            continue
        m = re.fullmatch(r"([^:]+): (.+)", line)
        if m and not m.group(1).startswith(("When", "Whenever", "At ")):
            b = Builder()
            body = m.group(2)
            sorcery = "Activate only as a sorcery" in body
            body = body.replace("Activate only as a sorcery.", "").replace("Activate only as a sorcery", "")
            effs = effects_of(body, b)
            ab = {"cost": parse_cost(m.group(1))}
            if b.targets:
                ab["targets"] = b.targets
            ab["effects"] = effs
            ab["text"] = line.replace("CARDNAME", name)
            if sorcery:
                ab["sorcery"] = True
            abilities.append(ab)
            continue
        raise Unsupported(line)

    if is_spell:
        if not spell_text:
            raise Unsupported("empty spell")
        b = Builder()
        effs = effects_of(" ".join(spell_text), b)
        spell = {}
        if b.targets:
            spell["targets"] = b.targets
        spell["effects"] = effs
        script["spell"] = spell
    if abilities:
        script["abilities"] = abilities
    if not script:
        raise Unsupported("nothing to script")  # fully covered by card data already
    return script


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    report_path = None
    if "--report" in sys.argv:
        report_path = sys.argv[sys.argv.index("--report") + 1]
        args = [a for a in args if a != report_path]
    if not args:
        print(__doc__)
        return 1
    opener = gzip.open if args[0].endswith(".gz") else open
    written = skipped = 0
    reasons = {}
    generated_names = []
    with opener(args[0], "rt", encoding="utf-8") as f:
        for line in f:
            card = json.loads(line)
            if card.get("layout") == "token" or "Token" in card.get("type_line", ""):
                continue
            legal = card.get("legalities", {})
            if legal and all(v == "not_legal" for v in legal.values()):
                continue
            path = os.path.join(SCRIPTS, card["oracle_id"] + ".json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as existing:
                    if not json.load(existing).get("generated"):
                        continue  # hand-written: never overwrite
            try:
                script = generate(card)
            except Unsupported as e:
                skipped += 1
                key = str(e)[:60]
                reasons[key] = reasons.get(key, 0) + 1
                continue
            written += 1
            generated_names.append(card["name"])
            if not dry:
                with open(path, "w", encoding="utf-8") as out:
                    json.dump({"name": card["name"], "generated": True, **script}, out, indent=2, ensure_ascii=False)
                    out.write("\n")
    print(f"generated {written} scripts, skipped {skipped} cards")
    if report_path:
        with open(report_path, "w", encoding="utf-8") as r:
            r.write(f"generated {written}\n\n")
            for name in sorted(generated_names):
                r.write(name + "\n")
            r.write("\nmost common unsupported lines:\n")
            for key, count in sorted(reasons.items(), key=lambda kv: -kv[1])[:200]:
                r.write(f"{count:6d}  {key}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
