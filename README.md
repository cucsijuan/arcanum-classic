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

## Generating scripts

`tools/generate_scripts.py <card-file.jsonl.gz>` writes scripts for cards whose rules text uses common, fixed
phrasings (damage, card draw, life, removal, pump, tokens, counters, simple triggers, activated abilities, lords,
auras, equipment). Only fully understood cards get a script; generated files carry `"generated": true` and
hand-written scripts are never overwritten. `--report report.txt` lists generated cards and the most common
unsupported lines, which is a good guide for what to support next.

Licensed under the GNU Affero General Public License v3.0 or later.
