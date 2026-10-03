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
    "first strike", "double strike", "indestructible", "hexproof", "shroud", "flash", "prowess",
    "kicker", "flashback", "ward", "changeling", "hexproof from", "loyalty",
    "equip", "enchant",  # derived from rules text by the engine's card factory
    # keyword actions and ability words: they label rules text the script spells out
    "scry", "surveil", "fight", "mill", "treasure", "food", "investigate",
    "raid", "landfall", "morbid", "threshold", "ferocious", "affinity", "double", "formidable", "alliance", "crew", "protection",
}
ABILITY_WORD = re.compile(r"^(Raid|Landfall|Morbid|Threshold|Ferocious|Formidable|Alliance) — ")
# Lines the engine derives from card data on its own.
DERIVED_LINE = re.compile(
    r"^(Kicker (\{[0-9WUBRGC]+\})+|Flashback (\{[0-9WUBRGC]+\})+|This spell can't be countered"
    r"|[Ww]ard( (\{[0-9WUBRGC]+\})+|—(?:(\{[0-9WUBRGC]+\})+, )?[Pp]ay \d+ life)"
    r"|\{T\}: Add \{[WUBRGC]\}((, | or |, or )\{[WUBRGC]\})*"
    r"|\{T\}: Add one mana of any color"
    r"|Equip (\{[0-9WUBRGC]+\})+"
    r"|Enchant (creature|land|artifact|enchantment|permanent)( you control)?"
    r"|This (land|creature|artifact|permanent) enters tapped)$")

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
SINGLE_FACE = {"normal"}


class Unsupported(Exception):
    pass


def num(word):
    if word == "X":
        return "X"
    if word in ("that much", "that many"):
        return "triggerAmount"
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
        "target creature or planeswalker": "creatureOrPlaneswalker",
        "target creature or planeswalker you control": "creatureOrPlaneswalker:you",
        "target creature or planeswalker an opponent controls": "creatureOrPlaneswalker:opponent",
        "target creature or planeswalker you don't control": "creatureOrPlaneswalker:opponent",
        "target planeswalker": "planeswalker",
        "target creature you control": "creature:you",
        "target creature you don't control": "creature:opponent",
        "target creature an opponent controls": "creature:opponent",
        "target player": "player",
        "target player or planeswalker": "playerOrPlaneswalker",
        "target opponent": "opponent",
        "target opponent or planeswalker": {"kind": "playerOrPlaneswalker", "controller": "opponent"},
        "target artifact": "artifact",
        "target enchantment": "enchantment",
        "target land": "land",
        "target permanent": "permanent",
        "target spell": "spell",
    }
    if phrase in table:
        return table[phrase]
    return filtered_target(phrase)


TYPE_WORDS = {"creature", "artifact", "enchantment", "land", "planeswalker", "permanent"}
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def filtered_target(phrase):
    """'target artifact or enchantment', 'up to one target creature', 'target tapped creature', ... -> target dict or None."""
    spec = {}
    m = re.fullmatch(r"up to one (.+)", phrase)
    if m:
        spec["optional"] = True
        phrase = m.group(1)
    m = re.fullmatch(r"another (target .+)", phrase)
    other = bool(m)
    if m:
        phrase = m.group(1)
    if not phrase.startswith("target "):
        return None
    rest = phrase[len("target "):]
    flt = {}
    if other:
        flt["other"] = True
    # graveyard cards
    m = re.fullmatch(r"(?:(creature|artifact|enchantment|land|instant or sorcery|permanent|nonland permanent) )?card from (your|a) graveyard", rest)
    if m:
        spec["kind"] = "graveyardCard"
        if m.group(2) == "your":
            spec["controller"] = "you"
        if m.group(1) == "instant or sorcery":
            flt["types"] = ["instant", "sorcery"]
        elif m.group(1) == "nonland permanent":
            flt["types"] = ["creature", "artifact", "enchantment", "planeswalker"]
        elif m.group(1) == "permanent":
            flt["types"] = ["creature", "artifact", "enchantment", "planeswalker", "land"]
        elif m.group(1):
            flt["types"] = [m.group(1)]
        if flt:
            spec["filter"] = flt
        return spec
    # spells
    m = re.fullmatch(r"(noncreature|creature|instant or sorcery|artifact or creature|(?:white|blue|black|red|green) or (?:white|blue|black|red|green)) spell", rest)
    if m:
        spec["kind"] = "spell"
        k = m.group(1)
        if k == "noncreature":
            flt["not"] = ["creature"]
        elif k.split(" or ")[0] in COLOR_WORDS:
            flt["colors"] = [COLOR_WORDS[c] for c in k.split(" or ")]
        else:
            flt["types"] = k.split(" or ")
        spec["filter"] = flt
        return spec
    # controller suffix
    for suffix, ctrl in ((" you control", "you"), (" you don't control", "opponent"), (" an opponent controls", "opponent")):
        if rest.endswith(suffix):
            spec["controller"] = ctrl
            rest = rest[: -len(suffix)]
            break
    # leading adjectives
    while True:
        m = re.match(r"(tapped|untapped|attacking or blocking|attacking|blocking|nontoken|nonland|(?:white|blue|black|red|green)(?: or (?:white|blue|black|red|green))?) (.+)", rest)
        if not m:
            break
        adj, rest = m.group(1), m.group(2)
        if adj == "tapped":
            flt["tapped"] = True
        elif adj == "untapped":
            flt["tapped"] = False
        elif adj == "attacking or blocking":
            flt["inCombat"] = True
        elif adj in ("attacking", "blocking"):
            flt["attacking" if adj == "attacking" else "inCombat"] = True
        elif adj == "nontoken":
            flt["token"] = False
        elif adj == "nonland":
            flt["not"] = ["land"]
        else:
            flt["colors"] = [COLOR_WORDS[c] for c in adj.split(" or ")]
    # trailing qualifiers
    qualified = False
    m = re.fullmatch(r"(.+?) with (flying|power (\d+) or greater|power (\d+) or less|toughness (\d+) or greater|mana value (\d+) or less|mana value (\d+) or greater)", rest)
    if m:
        rest = m.group(1)
        qualified = True
        q = m.group(2)
        if q == "flying":
            flt["keyword"] = "Flying"
        elif m.group(3):
            flt["minPower"] = int(m.group(3))
        elif m.group(4):
            flt["maxPower"] = int(m.group(4))
        elif m.group(5):
            flt["minToughness"] = int(m.group(5))
        elif m.group(6):
            flt["maxManaValue"] = int(m.group(6))
        elif m.group(7):
            flt["minManaValue"] = int(m.group(7))
    m = re.fullmatch(r"(.+?) that's ((?:white|blue|black|red|green)(?: or (?:white|blue|black|red|green))?)", rest)
    if m:
        rest = m.group(1)
        flt["colors"] = [COLOR_WORDS[c] for c in m.group(2).split(" or ")]
    walker = " or planeswalker" in rest
    rest = rest.replace(" or planeswalker", "")
    words = [w.strip(",") for w in re.split(r", or |, | or ", rest)]
    if not all(w in TYPE_WORDS for w in words):
        return None
    if qualified and len(words) > 1:
        return None  # "artifact, enchantment, or creature with flying": the qualifier applies to the last type only
    if words == ["creature"]:
        spec["kind"] = "creatureOrPlaneswalker" if walker else "creature"
    elif len(words) == 1 and words[0] != "planeswalker":
        spec["kind"] = words[0]
    else:
        spec["kind"] = "permanent"
        flt["types"] = [w for w in words if w != "permanent"]
    if flt:
        spec["filter"] = flt
    if set(spec) == {"kind"}:
        return spec["kind"]
    if set(spec) == {"kind", "controller"}:
        return spec["kind"] + ":" + spec["controller"]
    return spec


def base_kind(kind):
    return (kind if isinstance(kind, str) else kind["kind"]).split(":")[0]


class Builder:
    """Accumulates targets while effects are parsed, so effects can refer to "target", "target2", ..."""

    def __init__(self, triggered=False):
        self.targets = []
        self.triggered = triggered  # "that creature" refers to the object the trigger was about

    def add_target(self, kind):
        self.targets.append(kind)
        n = len(self.targets)
        return "target" if n == 1 else f"target{n}"

    def it(self):
        """'it' / 'that creature': the latest target if there is one, otherwise the source itself."""
        n = len(self.targets)
        return "self" if n == 0 else ("target" if n == 1 else f"target{n}")

    def subject(self, phrase):
        """'target creature you control' (adds a target), 'this creature', 'it' -> subject string."""
        if phrase in ("This creature", "this creature", "CARDNAME"):
            return "self"
        if phrase in ("That creature", "that creature", "That card", "that card") and self.triggered:
            return "triggered"
        if phrase in ("It", "it", "That creature", "that creature"):
            return self.it()
        kind = target_kind(phrase[0].lower() + phrase[1:])
        if kind is None or base_kind(kind) in ("player", "opponent", "spell", "any"):
            raise Unsupported(phrase)
        return self.add_target(kind)


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


PREDEFINED_TOKENS = {"Treasure", "Food", "Clue"}

CONDITIONS = {
    "you attacked this turn": "raid",
    "a creature died this turn": "morbid",
    "you gained life this turn": "gainedLife",
    "seven or more cards are in your graveyard": "threshold",
    "there are seven or more cards in your graveyard": "threshold",
    "you control a creature with power 4 or greater": "ferocious",
    "this spell was kicked": "kicked",
    "it was kicked": "kicked",
    "an opponent lost life this turn": "opponentLostLife",
    "it's your turn": "yourTurn",
}


def condition(text):
    """'you attacked this turn' -> 'raid'; 'you control a Wizard' -> {control: ...}. Raises Unsupported."""
    text = text.strip()
    if text in CONDITIONS:
        return CONDITIONS[text]
    m = re.fullmatch(r"you control (?:a|an|another) ([A-Z][a-z]+)", text)
    if m:
        return {"control": {"subtype": m.group(1), **({"other": True} if "another" in text else {})}}
    m = re.fullmatch(r"you control (\w+) or more (creatures|artifacts|enchantments|lands)", text)
    if m:
        return {"control": {"types": [m.group(2)[:-1]]}, "count": num(m.group(1))}
    m = re.fullmatch(r"you have (\d+) or more life", text)
    if m:
        return {"life": int(m.group(1))}
    raise Unsupported("if " + text)


def effect(sentence, b):
    """Parses one effect sentence (no trailing period). Returns a list of effect dicts."""
    s = sentence.strip()
    s = re.sub(r"^(Then|then) ", "", s)
    if s and s[0].islower() and not s.startswith(("it ",)):
        s = s[0].upper() + s[1:]
    # Compound sentences: "Draw a card, then discard a card", "You gain 2 life and draw a card".
    m = re.fullmatch(r"(.+?), then (?!shuffle)(.+)", s)
    if m:
        return effect(m.group(1), b) + effect(m.group(2), b)
    m = re.fullmatch(r"(Each opponent loses \w+ life|You gain \w+ life|You draw \w+ cards?|Draw \w+ cards?) and (you gain \w+ life|draw \w+ cards?|you lose \w+ life|scry \w+|surveil \w+)", s)
    if m:
        return effect(m.group(1), b) + effect(m.group(2), b)
    m = re.fullmatch(r"If (.+?), (.+)", s)
    if m:
        return [{"if": condition(m.group(1)), "then": effect(m.group(2), b)}]
    m = re.fullmatch(r"You may (.+)", s)
    if m:
        inner = m.group(1)
        return [{"may": inner[0].upper() + inner[1:] + "?", "effects": effect(inner, b)}]
    m = re.fullmatch(r"Return (target .+?card from your graveyard) to (your hand|the battlefield(?: tapped)?)", s)
    if m:
        kind = target_kind(m.group(1))
        if kind is None:
            raise Unsupported(s)
        subj = b.add_target(kind)
        if m.group(2) == "your hand":
            return [{"bounce": subj}]
        out = {"reanimate": subj}
        if m.group(2).endswith("tapped"):
            out["tapped"] = True
        return [out]
    m = re.fullmatch(r"Return up to (two|three) target (creature )?cards? from your graveyard to your hand", s)
    if m:
        out = []
        for _ in range(num(m.group(1))):
            spec = {"kind": "graveyardCard", "controller": "you", "optional": True}
            if m.group(2):
                spec["filter"] = {"types": ["creature"]}
            out.append({"bounce": b.add_target(spec)})
        return out
    m = re.fullmatch(r"Search your library for (a|up to two) (basic land|land|basic Forest|basic Plains|basic Island|basic Swamp|basic Mountain|creature|artifact|instant|sorcery) cards?, (?:reveal (?:it|them), )?put (?:it|them|that card) (into your hand|onto the battlefield(?: tapped)?), then shuffle", s)
    if m:
        what = m.group(2)
        flt = {}
        if what.startswith("basic"):
            flt["supertype"] = "basic"
            flt["types"] = ["land"]
            if what not in ("basic land",):
                flt["subtype"] = what.split()[1]
        else:
            flt["types"] = [what]
        out = {"search": flt, "count": 1 if m.group(1) == "a" else 2}
        dest = m.group(3)
        out["to"] = "hand" if dest == "into your hand" else "battlefield"
        if dest.endswith("tapped"):
            out["tapped"] = True
        return [out]
    m = re.fullmatch(r"(Target player|Target opponent|Each opponent|Each player) sacrifices? (a|an|two) (creature|creatures|artifact|enchantment|nonland permanent|creature or planeswalker)(?: of their choice)?", s)
    if m:
        who = {"Each opponent": "opponents", "Each player": "everyone"}.get(m.group(1))
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        kind = m.group(3).rstrip("s").replace(" or planeswalker", "")
        flt = {"types": ["creature", "artifact", "enchantment", "planeswalker"]} if kind == "nonland permanent" else {"types": [kind]}
        return [{"sacrifice": num(m.group(2)), "filter": flt, "who": who}]
    m = re.fullmatch(r"Destroy all (creatures|artifacts|enchantments|nonland permanents|creatures you don't control|creatures your opponents control)", s)
    if m:
        what = m.group(1)
        flt = {"types": ["creature", "artifact", "enchantment", "planeswalker"]} if what == "nonland permanents" else {"types": [what.split()[0][:-1]]}
        if "don't control" in what or "opponents" in what:
            flt["controller"] = "opponent"
        return [{"destroy": {"each": flt}}]
    m = re.fullmatch(r"(Creatures you control|Creatures your opponents control|Other creatures you control|All creatures|Each creature you control|Attacking creatures you control) gets? ([+-]\d+)/([+-]\d+)(?: and gain (.+?))? until end of turn", s)
    if m:
        flt = {"types": ["creature"]}
        who = m.group(1)
        if "your opponents" in who:
            flt["controller"] = "opponent"
        elif "you control" in who:
            flt["controller"] = "you"
        if who.startswith("Other"):
            flt["other"] = True
        if who.startswith("Attacking"):
            flt["attacking"] = True
        out = {"pump": [int(m.group(2)), int(m.group(3))], "what": {"each": flt}}
        if m.group(4):
            out["keywords"] = keywords_list(m.group(4))
        return [out]
    m = re.fullmatch(r"Creatures you control gain (.+) until end of turn", s)
    if m:
        return [{"pump": [0, 0], "what": {"each": {"types": ["creature"], "controller": "you"}}, "keywords": keywords_list(m.group(1))}]
    m = re.fullmatch(r"(?:CARDNAME|This \w+|It) deals (\w+) damage to each (creature|creature without flying|creature with flying|opponent|player|creature and each player|creature your opponents control)", s)
    if m:
        n = num(m.group(1))
        what = m.group(2)
        if what == "opponent":
            return [{"damage": n, "to": "opponents"}]
        if what == "player":
            return [{"damage": n, "to": "everyone"}]
        flt = {"types": ["creature"]}
        if "without flying" in what:
            flt["without"] = "Flying"
        if "with flying" in what:
            flt["keyword"] = "Flying"
        if "opponents" in what:
            flt["controller"] = "opponent"
        out = [{"damage": n, "to": {"each": flt}}]
        if "each player" in what:
            out.append({"damage": n, "to": "everyone"})
        return out
    m = re.fullmatch(r"Put (\w+) \+1/\+1 counters? on each (creature you control|other creature you control)", s)
    if m:
        flt = {"types": ["creature"], "controller": "you"}
        if m.group(2).startswith("other"):
            flt["other"] = True
        return [{"counters": num(m.group(1)), "what": {"each": flt}}]
    m = re.fullmatch(r"(Scry|Surveil) (\d+)", s)
    if m:
        return [{m.group(1).lower(): int(m.group(2))}]
    if s == "Investigate":
        return [{"tokens": 1, "token": "Clue"}]
    m = re.fullmatch(r"Create (\w+) (Treasure|Food|Clue) tokens?", s)
    if m:
        return [{"tokens": num(m.group(1)), "token": m.group(2)}]
    m = re.fullmatch(r"(Target creature you control|This creature|CARDNAME|It|it) fights (target creature(?: you don't control| an opponent controls)?|up to one target creature you don't control)", s)
    if m:
        first = "self" if not m.group(1).startswith("Target") else b.add_target("creature:you")
        second = b.add_target("creature" if m.group(2) == "target creature" else "creature:opponent")
        return [{"fight": first, "with": second}]
    m = re.fullmatch(r"(Target player|Target opponent|Each opponent|Each player|You) discards? (\w+) cards?", s)
    if m:
        who = {"Each opponent": "opponents", "Each player": "everyone", "You": "you"}.get(m.group(1))
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        return [{"discard": num(m.group(2)), "who": who}]
    m = re.fullmatch(r"Discard (\w+) cards?", s)
    if m:
        return [{"discard": num(m.group(1)), "who": "you"}]
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
    m = re.fullmatch(r"You gain (\w+|that much) life", s)
    if m:
        return [{"gainLife": num(m.group(1))}]
    m = re.fullmatch(r"(That player|That creature's controller) (loses|gains) (\w+) life", s)
    if m:
        return [{("loseLife" if m.group(2) == "loses" else "gainLife"): num(m.group(3)), "who": "triggeredPlayer"}]
    m = re.fullmatch(r"(?:CARDNAME|This creature) deals (\w+) damage to that player", s)
    if m:
        return [{"damage": num(m.group(1)), "to": "triggeredPlayer"}]
    m = re.fullmatch(r"You gain (\w+) life for each (creature|artifact|land|Gate|[A-Z][a-z]+) you control", s)
    if m:
        f = {"types": [m.group(2)]} if m.group(2) in ("creature", "artifact", "land") else {"subtype": m.group(2)}
        return [{"gainLife": {"count": f, "times": num(m.group(1))}}]
    m = re.fullmatch(r"You gain (\w+) life for each attacking (creature|[A-Z][a-z]+)(?: you control)?", s)
    if m:
        f = {"types": ["creature"]} if m.group(2) == "creature" else {"subtype": m.group(2)}
        f["controller"] = "you"
        return [{"gainLife": {"attacking": f, "times": num(m.group(1))}}]
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
        if kind is None or base_kind(kind) in ("any", "player", "opponent", "spell"):
            raise Unsupported(s)
        key = {"Destroy": "destroy", "Exile": "exile", "Tap": "tap", "Untap": "untap"}[m.group(1)]
        return [{key: b.add_target(kind)}]
    m = re.fullmatch(r"Return (target .+?) to its owner's hand", s)
    if m:
        kind = target_kind(m.group(1))
        if kind is None or base_kind(kind) in ("any", "player", "opponent", "spell"):
            raise Unsupported(s)
        return [{"bounce": b.add_target(kind)}]
    m = re.fullmatch(r"Counter (target .*spell)", s)
    if m and target_kind(m.group(1)) is not None and base_kind(target_kind(m.group(1))) == "spell":
        return [{"counter": b.add_target(target_kind(m.group(1)))}]
    m = re.fullmatch(r"Mill (\w+) cards?", s)
    if m:
        return [{"mill": num(m.group(1)), "who": "you"}]
    m = re.fullmatch(r"(Target player|Target opponent|Each opponent|You) mills? (\w+) cards?", s)
    if m:
        who = {"Each opponent": "opponents", "You": "you"}.get(m.group(1))
        if who is None:
            who = b.add_target("player" if m.group(1) == "Target player" else "opponent")
        return [{"mill": num(m.group(2)), "who": who}]
    m = re.fullmatch(r"((?:Up to one )?(?:[Aa]nother )?[Tt]arget [^,]+?|This creature|CARDNAME|It|it|That creature) gets ([+-](?:\d+|X))/([+-](?:\d+|X)) (?:and gains " + KW + r"(?: and " + KW + r")? )?until end of turn", s)
    if m:
        subj = b.subject(m.group(1))
        def amount(v):
            return v.lstrip("+") if "X" not in v else ("-X" if v.startswith("-") else "X")
        p_, t_ = amount(m.group(2)), amount(m.group(3))
        out = {"pump": [int(p_) if p_.lstrip("-").isdigit() else p_, int(t_) if t_.lstrip("-").isdigit() else t_], "what": subj}
        kws = [k for k in (m.group(4), m.group(5)) if k]
        if kws:
            out["keywords"] = keywords_list(" and ".join(kws))
        return [out]
    m = re.fullmatch(r"((?:Up to one )?(?:[Aa]nother )?[Tt]arget [^,]+?|This creature|CARDNAME|It|it|That creature) gains (.+) until end of turn", s)
    if m:
        return [{"pump": [0, 0], "what": b.subject(m.group(1)), "keywords": keywords_list(m.group(2))}]
    m = re.fullmatch(r"Put (\w+|that many) \+1/\+1 counters? on ((?:up to one )?(?:another )?target [^,]+?|this creature|CARDNAME|it|that creature)", s)
    if m:
        return [{"counters": num(m.group(1)), "what": b.subject(m.group(2))}]
    m = re.fullmatch(r"Put (\w+) \+1/\+1 counters? on each of up to (two|three) (other )?target creatures(?: you control)?", s)
    if m:
        out = []
        for _ in range(num(m.group(2))):
            spec = {"kind": "creature", "optional": True}
            if "you control" in s:
                spec["controller"] = "you"
            if m.group(3):
                spec["filter"] = {"other": True}
            out.append({"counters": num(m.group(1)), "what": b.add_target(spec)})
        return out
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
    (r"When (?:this \w+|CARDNAME) enters, (.+)", "enters"),
    (r"Whenever (?:this creature|CARDNAME) blocks, (.+)", "blocks"),
    (r"Whenever (?:this creature|CARDNAME) attacks or blocks, (.+)", "attacksOrBlocks"),
    (r"Whenever a land you control enters, (.+)", "landfall"),
    (r"Whenever you gain life, (.+)", "gainLife"),
    (r"At the beginning of combat on your turn, (.+)", "beginCombat"),
    (r"Whenever you attack, (.+)", "youAttack"),
    (r"Whenever an opponent loses life, (.+)", "opponentLosesLife"),
    (r"Whenever you draw a card, (.+)", "draw"),
    (r"At the beginning of (?:each|the) end step, (.+)", "eachEndStep"),
    (r"At the beginning of each combat, (.+)", "eachBeginCombat"),
    (r"At the beginning of each upkeep, (.+)", "eachUpkeep"),
    (r"Whenever (?:this creature|CARDNAME) becomes tapped, (.+)", "becomesTapped"),
    (r"Whenever one or more creatures you control attack, (.+)", "youAttack"),
    (r"When (?:this creature|CARDNAME) dies, (.+)", "dies"),
    (r"Whenever (?:this creature|CARDNAME) attacks, (.+)", "attacks"),
    (r"At the beginning of your upkeep, (.+)", "upkeep"),
    (r"At the beginning of your end step, (.+)", "endStep"),
    (r"Whenever (?:this creature|CARDNAME) deals combat damage to a player, (.+)", "combatDamageToPlayer"),
]

PLURALS = {"Elves": "Elf", "Wolves": "Wolf", "Dwarves": "Dwarf"}


def singular(word):
    return PLURALS.get(word, word[:-1] if word.endswith("s") else word)


def filtered_trigger(line):
    """Triggers on other objects: returns (trigger, filter, rest) or None."""
    m = re.fullmatch(r"Whenever (?:CARDNAME|this creature) or another (nontoken )?(creature|[A-Z][a-z]+)( you control)? (enters|dies), (.+)", line)
    if m:
        f = {"types": ["creature"], "controller": "you" if m.group(3) else "any"}
        if m.group(2) != "creature":
            f["subtype"] = m.group(2)
        if m.group(1):
            f["token"] = False
        return ("creatureEnters" if m.group(4) == "enters" else "creatureDies"), f, m.group(5)
    m = re.fullmatch(r"Whenever (a|another) (nontoken )?((?:white|blue|black|red|green) )?(creature|[A-Z][a-z]+)( you control)?(?: with power (\d+) or (less|greater))? attacks, (.+)", line)
    if m:
        f = {"types": ["creature"], "controller": "you" if m.group(5) else "any"}
        if m.group(1) == "another":
            f["other"] = True
        if m.group(2):
            f["token"] = False
        if m.group(3):
            f["colors"] = [COLOR_WORDS[m.group(3).strip()]]
        if m.group(4) != "creature":
            f["subtype"] = m.group(4)
        if m.group(6):
            f["maxPower" if m.group(7) == "less" else "minPower"] = int(m.group(6))
        return "creatureAttacks", f, m.group(8)
    m = re.fullmatch(r"Whenever (a|another) (nontoken )?(creature|[A-Z][a-z]+)( you control)? with power (\d+) or (less|greater) enters, (.+)", line)
    if m:
        f = {"types": ["creature"], "controller": "you" if m.group(4) else "any", ("maxPower" if m.group(6) == "less" else "minPower"): int(m.group(5))}
        if m.group(1) == "another":
            f["other"] = True
        if m.group(2):
            f["token"] = False
        if m.group(3) != "creature":
            f["subtype"] = m.group(3)
        return "creatureEnters", f, m.group(7)
    m = re.fullmatch(r"Whenever an opponent casts (?:a|an) ((?:white|blue|black|red|green) or (?:white|blue|black|red|green) )?(spell|instant or sorcery spell|noncreature spell|creature spell), (.+)", line)
    if m:
        f = {}
        if m.group(1):
            f["colors"] = [COLOR_WORDS[c] for c in m.group(1).strip().split(" or ")]
        if m.group(2) == "instant or sorcery spell":
            f["types"] = ["instant", "sorcery"]
        elif m.group(2) == "noncreature spell":
            f["not"] = ["creature"]
        elif m.group(2) == "creature spell":
            f["types"] = ["creature"]
        return "opponentCastsSpell", f, m.group(3)
    m = re.fullmatch(r"Whenever a creature you control (?:with (deathtouch|flying) )?deals combat damage to a player, (.+)", line)
    if m:
        f = {"types": ["creature"], "controller": "you"}
        if m.group(1):
            f["keyword"] = m.group(1).capitalize()
        return "creatureCombatDamageToPlayer", f, m.group(2)
    m = re.fullmatch(r"Whenever you cast a spell, (.+)", line)
    if m:
        return "castSpell", {}, m.group(1)
    m = re.fullmatch(r"Whenever (a|another) (nontoken )?(creature|[A-Z][a-z]+)( you control| an opponent controls)? (enters|dies), (.+)", line)
    if m:
        f = {}
        if m.group(3) != "creature":
            f["subtype"] = m.group(3)
        f["types"] = ["creature"]
        if m.group(1) == "another":
            f["other"] = True
        if m.group(2):
            f["token"] = False
        f["controller"] = {" you control": "you", " an opponent controls": "opponent", None: "any"}[m.group(4)]
        return ("creatureEnters" if m.group(5) == "enters" else "creatureDies"), f, m.group(6)
    m = re.fullmatch(r"Whenever you cast (?:a|an) (noncreature|creature|instant or sorcery|instant|sorcery|enchantment|artifact) spell, (.+)", line)
    if m:
        kind = m.group(1)
        f = {"not": ["creature"]} if kind == "noncreature" else {"types": kind.split(" or ")}
        return "castSpell", f, m.group(2)
    return None


def parse_cost(cost):
    parts = []
    for raw in [c.strip() for c in cost.split(",")]:
        if raw == "{T}":
            parts.append("{T}")
        elif re.fullmatch(r"Sacrifice (this creature|this artifact|this enchantment|this land|this permanent|CARDNAME)", raw):
            parts.append("sacrifice")
        elif re.fullmatch(r"(\{[0-9WUBRGCX]+\})+", raw):
            parts.append(raw)
        elif raw in ("Sacrifice another creature", "Sacrifice a creature"):
            parts.append("sacrifice:creature")
        elif raw == "Sacrifice an artifact":
            parts.append("sacrifice:artifact")
        elif raw == "Discard a card":
            parts.append("discard")
        elif re.fullmatch(r"Pay (\d+) life", raw):
            parts.append("life:" + re.fullmatch(r"Pay (\d+) life", raw).group(1))
        elif raw == "Exile this card from your graveyard":
            parts.append("exileFromGraveyard")
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
    m = re.fullmatch(r"Other ([A-Z][a-z]+) you control get ([+-]\d+)/([+-]\d+)(?: and have (.+))?", line)
    if m and m.group(1) not in ("creatures",):
        st = {"affects": "creatures:you", "other": True, "subtype": singular(m.group(1)), "pump": [int(m.group(2)), int(m.group(3))]}
        if m.group(4):
            st["keywords"] = keywords_list(m.group(4))
        return st
    m = re.fullmatch(r"(Other )?[Cc]reatures you control have (.+)", line)
    if m:
        st = {"affects": "creatures:you", "pump": [0, 0], "keywords": keywords_list(m.group(2))}
        if m.group(1):
            st["other"] = True
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


SPELL_TYPES = {"Instant and sorcery": ["instant", "sorcery"], "Creature": ["creature"], "Noncreature": None,
               "Artifact": ["artifact"], "Enchantment": ["enchantment"]}


def card_flag(line):
    """Card-wide rules written as a single line: returns script fields, or None."""
    if line == "This spell can't be countered":
        return {"uncounterable": True}
    if line in ("This creature attacks each combat if able", "CARDNAME attacks each combat if able"):
        return {"attacksEachCombat": True}
    if line in ("This creature doesn't untap during your untap step", "CARDNAME doesn't untap during your untap step"):
        return {"doesntUntap": True}
    if line == "You have hexproof":
        return {"givesHexproof": True}
    if line == "Players can't gain life":
        return {"playersCantGainLife": True}
    m = re.fullmatch(r"Hexproof from (white|blue|black|red|green)", line)
    if m:
        return {"hexproofFrom": [COLOR_WORDS[m.group(1)]]}
    if re.fullmatch(r"(Kicker|Flashback) (\{[0-9WUBRGC]+\})+", line):
        return {"_derived": True}
    if re.fullmatch(r"[Ww]ard( (\{[0-9WUBRGC]+\})+|—(?:(\{[0-9WUBRGC]+\})+, )?[Pp]ay \d+ life)", line):
        return {"_derived": True}
    m = re.fullmatch(r"As an additional cost to cast this spell, (discard a card|sacrifice a creature|sacrifice an artifact|pay (\d+) life)", line)
    if m:
        what = m.group(1)
        if what == "discard a card":
            return {"additionalCost": {"discard": 1}}
        if what.startswith("pay"):
            return {"additionalCost": {"life": int(m.group(2))}}
        return {"additionalCost": {"sacrifice": {"types": [what.split()[-1]]}}}
    m = re.fullmatch(r"This spell costs \{(\d+)\} less to cast if (.+)", line)
    if m:
        return {"costReduction": {"amount": int(m.group(1)), "if": condition(m.group(2))}}
    m = re.fullmatch(r"This spell costs \{1\} less to cast for each (creature|artifact|land|Gate|[A-Z][a-z]+) you control", line)
    if m:
        f = {"types": [m.group(1)]} if m.group(1) in ("creature", "artifact", "land") else {"subtype": m.group(1)}
        return {"costReduction": {"amount": 1, "perPermanent": f}}
    m = re.fullmatch(r"This spell costs \{1\} less to cast for each instant and sorcery card in your graveyard", line)
    if m:
        return {"costReduction": {"amount": 1, "perGraveyardCard": {"types": ["instant", "sorcery"]}}}
    return None


def is_keyword_line(line, keywords):
    parts = [p.strip().lower() for p in line.split(",")]
    kws = {k.lower() for k in keywords}
    return all(p in kws or re.fullmatch(r"ward (\{[0-9wubrgc]+\})+", p) for p in parts)


NTH = [
    (r"Whenever you draw your second card each turn, (.+)", "draw", 2, None),
    (r"Whenever you gain life for the first time each turn, (.+)", "gainLife", 1, None),
    (r"Whenever you gain life for the first time during each of your turns, (.+)", "gainLife", 1, "yourTurn"),
]


def trigger_ability(line):
    """A triggered ability line -> script dict (without text), or None if it isn't one we know."""
    trig = None
    extra = {}
    for pattern, trigger in TRIGGERS:
        m = re.fullmatch(pattern, line)
        if m:
            trig = (trigger, None, m.group(1))
            break
    if trig is None:
        for pattern, trigger, nth, cond in NTH:
            m = re.fullmatch(pattern, line)
            if m:
                trig = (trigger, None, m.group(1))
                extra["nth"] = nth
                if cond:
                    extra["if"] = cond
                break
    if trig is None:
        trig = filtered_trigger(line)
    if trig is None:
        return None
    trigger, flt, rest = trig
    ab = {"trigger": trigger, **extra}
    if flt:
        ab["filter"] = flt
    m = re.fullmatch(r"if (.+?), (.+)", rest)
    if m:
        ab["if"] = condition(m.group(1))
        rest = m.group(2)
    b = Builder(triggered=flt is not None)
    effs = effects_of(rest, b)
    if b.targets:
        ab["targets"] = b.targets
    ab["effects"] = effs
    return ab


MODE_HEADER = re.compile(r"^(.*?)(?:, )?[Cc]hoose (one|two|one or both|one or more) —$")


def group_modes(lines):
    """Turns a 'Choose one —' line plus its '• ...' lines into one (header, count, upTo, bullets) item."""
    out = []
    i = 0
    while i < len(lines):
        m = MODE_HEADER.fullmatch(lines[i])
        if m:
            bullets = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("•"):
                bullets.append(lines[j].lstrip("• ").strip())
                j += 1
            if not bullets:
                raise Unsupported("modes")
            count = {"one": 1, "two": 2, "one or both": 2, "one or more": len(bullets)}[m.group(2)]
            out.append((m.group(1).strip(), count, m.group(2) in ("one or both", "one or more"), bullets))
            i = j
            continue
        out.append(lines[i])
        i += 1
    return out


def modes_of(count, up_to, bullets, name):
    modes = []
    for text in bullets:
        b = Builder()
        effs = effects_of(text, b)
        mode = {"text": text.replace("CARDNAME", name)}
        if b.targets:
            mode["targets"] = b.targets
        mode["effects"] = effs
        modes.append(mode)
    out = {"modes": modes}
    if count != 1:
        out["chooseCount"] = count
    if up_to:
        out["upTo"] = True
    return out


def generate(card):
    if card.get("layout") not in SINGLE_FACE:
        raise Unsupported("layout")
    for k in card.get("keywords", []):
        if k.lower() not in ENGINE_KEYWORDS:
            raise Unsupported("keyword " + k)
    for stat in ("power", "toughness"):
        if stat in card and not re.fullmatch(r"-?\d+", card[stat]):
            raise Unsupported("stat")
    if re.search(r"/P\}", card.get("mana_cost", "")):
        raise Unsupported("cost")

    name = card["name"]
    text = re.sub(r"\s*\([^)]*\)", "", card.get("oracle_text", ""))
    text = text.replace(name, "CARDNAME")
    if "Legendary" in card.get("type_line", "") and "," in name:
        text = text.replace(name.split(",")[0], "CARDNAME")  # "Whenever Alesha attacks"
    types = card.get("type_line", "")
    is_spell = "Instant" in types or "Sorcery" in types
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    lines = group_modes(lines)
    script = {}
    abilities = []
    spell_text = []
    for line in lines:
        if isinstance(line, tuple):  # (header, count, upTo, bullets)
            header, count, up_to, bullets = line
            modal = modes_of(count, up_to, bullets, name)
            if is_spell and header == "":
                if spell_text:
                    raise Unsupported("modal spell with other text")
                script["spell"] = modal
                continue
            trig = None
            for pattern, trigger in TRIGGERS:
                m = re.fullmatch(pattern, header + ", X")
                if m:
                    trig = (trigger, None)
                    break
            if trig is None and filtered_trigger(header + ", X") is not None:
                t, f, _ = filtered_trigger(header + ", X")
                trig = (t, f)
            if trig is None:
                raise Unsupported("modal " + header)
            ab = {"trigger": trig[0]}
            if trig[1]:
                ab["filter"] = trig[1]
            ab.update(modal)
            ab["text"] = (header + " choose one —").replace("CARDNAME", name)
            abilities.append(ab)
            continue
        original = line
        line = ABILITY_WORD.sub("", line)
        bare = line.rstrip(".")
        if DERIVED_LINE.fullmatch(bare) or is_keyword_line(bare, card.get("keywords", [])):
            continue
        flags = card_flag(bare)
        if flags:
            script.update(flags)
            continue
        if is_spell:
            spell_text.append(line)
            continue
        m = re.fullmatch(r"(?:This creature|CARDNAME) enters with (\w+) \+1/\+1 counters? on it\.?", line)
        if m:
            script["entersWithCounters"] = num(m.group(1))
            continue
        flags = card_flag(bare)
        if flags:
            script.update(flags)
            continue
        st = static(bare)
        if st is not None:
            abilities.append({"static": st, "text": line.replace("CARDNAME", name)})
            continue
        # "When this creature enters or dies, ..." / "Whenever this creature enters or attacks, ...": one ability per event.
        m = re.fullmatch(r"(When|Whenever) (this creature|CARDNAME) (enters|attacks) or (dies|attacks), (.+)", line)
        variants = [f"{m.group(1)} {m.group(2)} {m.group(3)}, {m.group(5)}", f"{m.group(1)} {m.group(2)} {m.group(4)}, {m.group(5)}"] if m else [line]
        made = []
        for variant in variants:
            ab = trigger_ability(variant)
            if ab is None:
                break
            ab["text"] = original.replace("CARDNAME", name)
            made.append(ab)
        if len(made) == len(variants):
            abilities.extend(made)
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

    if is_spell and "spell" not in script:
        if not spell_text:
            raise Unsupported("empty spell")
        b = Builder()
        effs = effects_of(" ".join(spell_text), b)
        spell = {}
        if b.targets:
            spell["targets"] = b.targets
        spell["effects"] = effs
        script["spell"] = spell
    script.pop("_derived", None)
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
