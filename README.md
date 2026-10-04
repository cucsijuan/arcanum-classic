# arcanum-classic

Content module for [Arcanum](https://github.com/cucsijuan/arcanum): where to download card data and images,
card ability scripts, formats and sample decks. Arcanum downloads and installs this module at runtime; no card
data or images are stored in this repository.

| File | Purpose |
|------|---------|
| `manifest.json` | Module id, version, license and engine API version |
| `sources.json` | Card data and image sources fetched at runtime |
| `scripts/` | Card ability scripts |
| `formats/` | Deck construction rules |
| `decks/` | Sample decks |
| `sets/` | Card sets: their cards, how their boosters are made (sheets and slots) and limited settings |
| `cubes/` | Cube lists for cube drafts (deck-list format) |

## Generating scripts

`tools/generate_scripts.py <card-file.jsonl.gz>` writes scripts for cards whose rules text uses common, fixed
phrasings (damage, card draw, life, removal, pump, tokens, counters, simple triggers, activated abilities, lords,
auras, equipment). Only fully understood cards get a script; generated files carry `"generated": true` and
hand-written scripts are never overwritten. `--report report.txt` lists generated cards and the most common
unsupported lines, which is a good guide for what to support next.

## Sets and boosters

A set file lists its cards and may describe its booster: `sheets` pick printings of the set (by rarity, booster
flag, basic or not, names, collector numbers, or another set's numbers) and `slots` say how many cards come from
which sheets, with relative weights (`{"count": 1, "sheets": {"rare": 857, "mythic": 143}}`). Cards are not repeated
within a booster except in `wildcard` slots. `limited` sets the boosters per player in a draft and in sealed.

`tools/build_set_decks.py` builds sample decks for a set (with the printings file, every line names the set's
printing); `tools/build_cube.py` builds a 360-card cube of supported cards.

Licensed under the GNU Affero General Public License v3.0 or later.
