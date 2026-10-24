#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Builds search/tags.json.gz: the cards and printings behind the card search's curated is: values (land cycle
nicknames, is:bear, is:commander, is:etb, is:atypical...), as the card data's source decides them.

Usage: tools/search_tags.py

Asks the card data source's search for each value and keeps its oracle ids (a card-level value) or printing ids (a
printing-level one). The game's search uses these lists for those values, so they find exactly what the source's own
search finds; values the card data itself says (layouts, promo types, frames, finishes) are worked out by the game.
Run it again when a new set comes out (the source tags its cards), then check the counts it prints.
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "search", "tags.json.gz")
SEARCH = "https://api.scryfall.com/cards/search?unique={unique}&q={query}"
USER_AGENT = "arcanum-classic search_tags"
PAUSE = 0.5  # the source asks for at most 10 requests a second, and slows down busy clients further

# Card-level values: the cards the source tags with each nickname.
CARDS = [
    "dual", "shockland", "fetchland", "checkland", "fastland", "slowland", "painland", "filterland", "gainland",
    "scryland", "surveilland", "bounceland", "canopyland", "bikeland", "tangoland", "shadowland", "storageland",
    "triland", "tricycleland", "pathway", "bondland", "manland",
    "bear", "vanilla", "frenchvanilla", "modal", "outlaw", "party", "historic", "commander", "brawler",
    "duelcommander", "oathbreaker", "paupercommander", "partner", "companion", "hybrid", "phyrexian", "spikey", "etb",
    "meldpart", "meldresult", "class", "prepare", "augment", "host", "contentwarning", "gamechanger", "reserved",
]

# Printing-level values: the printings the source tags (is:default is every printing that isn't atypical).
PRINTINGS = ["atypical", "spotlight", "scryfallpreview"]

# Other names the source's search takes for the same values.
ALIASES = {
    "snarl": "shadowland", "battleland": "tangoland", "trikeland": "tricycleland", "triome": "tricycleland",
    "karoo": "bounceland", "canland": "canopyland", "horizonland": "canopyland", "cycleland": "bikeland",
    "bicycleland": "bikeland", "creatureland": "manland", "crowdland": "bondland",
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"data": [], "has_more": False}  # no card has it
            if e.code != 429:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or min(60, 2 ** attempt))  # asked to slow down
    raise RuntimeError(f"gave up on {url}")


def ids(value, unique, key):
    url = SEARCH.format(unique=unique, query=urllib.parse.quote(f"is:{value}"))
    found = []
    while url:
        page = fetch(url)
        if page.get("warnings"):
            raise RuntimeError(f"is:{value}: {page['warnings']}")
        found += [card[key] for card in page["data"] if key in card]
        url = page.get("next_page") if page.get("has_more") else None
        time.sleep(PAUSE)
    return sorted(set(found))


def main():
    tags = {"aliases": ALIASES, "cards": {}, "printings": {}}
    for value in CARDS:
        tags["cards"][value] = ids(value, "cards", "oracle_id")
        print(f"is:{value}: {len(tags['cards'][value])} cards", file=sys.stderr)
    for value in PRINTINGS:
        tags["printings"][value] = ids(value, "prints", "id")
        print(f"is:{value}: {len(tags['printings'][value])} printings", file=sys.stderr)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as out:
        json.dump(tags, out, separators=(",", ":"))
    print(f"Wrote {os.path.relpath(OUT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
