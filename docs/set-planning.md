# Choosing the next card set

`tools/set_planner.py` (with the engine repository's `tools/SupportDump`) answers "which set should we do next so that later sets get easier": for every paper set it
counts the cards the engine already runs, the ones that only need a script, and the ones blocked by a mechanic the
engine doesn't have; and for each candidate set, how many cards of *other* sets its new mechanics would unblock.

## Running it

```sh
# 1. Which cards run with the current module (writes support.tsv and keywords.txt).
CARDS=$(ls -t ~/.local/share/godot/app_userdata/Arcanum/card_data/arcanum-classic/cards.*.jsonl.gz | head -1)
# ENGINE is the engine repository's checkout, whatever its folder is called on this machine (e.g. ../arcanum).
dotnet run --project "$ENGINE/tools/SupportDump" -c Release -- . "$CARDS" /tmp/plan   # from this repository

# 2. Rankings.
python3 tools/set_planner.py "$CARDS" /tmp/plan --mechanics          # missing mechanics, by cards each one alone unblocks
python3 tools/set_planner.py "$CARDS" /tmp/plan --types expansion,core # candidate sets, best value per new mechanic first
python3 tools/set_planner.py "$CARDS" /tmp/plan --sort unblocks         # candidate sets, most cards unblocked elsewhere
python3 tools/set_planner.py "$CARDS" /tmp/plan --detail <set code>     # one set: what blocks it
```

On Windows the card data lives under `%APPDATA%/Godot/app_userdata/Arcanum/card_data/arcanum-classic/`, and Python
needs `python -X utf8 tools/set_planner.py …` to read the card names (it otherwise uses the system code page).

Columns: *unblocks* = cards in other sets whose every missing mechanic the candidate brings; *per mechanic* = that divided
by how many new mechanics the candidate needs (the cost); *run* / *script only* / *blocked* = the candidate's own cards.

## How it decides

- A card is **blocked** when the card data lists a keyword (or keyword action) that is neither handled by the card
  importer (`CardFactory.SupportedKeywords`, dumped by SupportDump) nor listed in `tools/engine-mechanics.txt`.
- Ability words (Landfall, Raid, Domain…) have no rules of their own, so they never block: a card with one needs a script.
- "Script only" doesn't mean the script vocabulary already has every effect the card uses; it's the cheap part, not free.
- Double-faced cards show up as the `Transform` keyword (and Daybound/Nightbound, Disturb, Meld…).

## Keeping it right

When a mechanic is implemented in the engine, add its name (as the card data spells it) to `tools/engine-mechanics.txt`.
Nothing else needs updating: the card data and the module are read fresh each run.
