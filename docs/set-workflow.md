# Adding a card set

The steps that take a set from "not in the module" to "released". The engine side (where rules code lives and how a mechanic
goes in) is in the engine repository's `docs/engine-map.md`; the script vocabulary is its `docs/card-scripts.md`.

```sh
CARDS=$(ls -t ~/.local/share/godot/app_userdata/Arcanum/card_data/arcanum-classic/cards.*.jsonl.gz | head -1)
ENGINE=../g-mtg   # the engine repository's checkout
```

## 1. Choose the set

Run `tools/set_planner.py` as [set-planning.md](set-planning.md) explains; `--detail <code>` lists what blocks the set.

## 2. See what's missing

```sh
dotnet run --project "$ENGINE/tools/SupportDump" -c Release -- . "$CARDS" /tmp/plan
```

`support.tsv` says which cards are fully supported; `why.tsv` says why each other card isn't (an unscripted keyword, a rules line the
importer doesn't understand, a script effect the engine lacks). Filter both by the set's cards. Double-faced cards are listed by their
front face's name.

## 3. Scripts

- `tools/generate_scripts.py "$CARDS"` writes scripts for cards with fixed phrasings (`"generated": true`), including preparation
  cards, "This creature enters prepared" and "Empower Jace N". A script with comments is hand-written and is never overwritten.
- `tools/set_triage.py "$CARDS" /tmp/plan <code> --out triage.md` reports the cards that still need scripts: those blocked by something
  besides the script, grouped by reason, then script-only cards, fewest new lines first. Each rules line is marked `=` (a script has
  it), `≈` (same wording, other numbers or mana), `+` (a keyword) or `·` (new), with the reference script. `--write` also copies scripts
  for cards with the same rules text and composes scripts from existing abilities; without it nothing is written to `scripts/`. After
  `--write`, repeat step 2. Hand-written scripts start from the report's reference scripts.
- Every other card gets a hand-written `scripts/<oracle id>.json`. Write exactly what the card does: every choice and restriction.
- A mechanic the engine lacks goes into the engine first (see `engine-map.md`), with a test, then the script uses it.
- New keywords go into `tools/engine-mechanics.txt` so the planner knows them.
- Repeat step 2 until every card of the set is supported.

## 4. The set file

`sets/<code>.json`: the card list, pack image, limited settings, and the booster sheets and slots exactly as the real product
(official collation percentages; printings by collector number, foil and showcase treatments as printed). Write down any ratio that had
to be derived from published numbers. Check the packs: every sheet non-empty, the right pack size, no unsupported card.

A booster kind (under `boosters`, e.g. `collector`) may give its own `"pack": {"image": ..., "seals": [top, bottom]}` like the set's
pack, when its picture differs. Measure the seals on that picture: the crimped top and bottom ends, as fractions of the picture
height. Without them the defaults are 0.07 and 0.06. A kind without its own pack uses the set's.

A sheet that holds surge foil printings is marked `"surge": true`. Treatments with different official odds go in separate sheets,
one per treatment, and the slot weights are those odds (the per-slot percentages as published).

## 5. Scenes

A set whose cards' art joins into one picture (a scene) lists the scenes in its set file, as `"scenes"`: each with a
`name`, `columns` (cards across; all in one row when left out) and `cards`, the collector numbers row by row from the top
left. A place holds one number, or a list of numbers when the same art is printed under more than one (a surge foil under
another number, for one). A place without a number is an error. The career desk then shows the scenes (`Scenes (N)`).

Research the scenes from the printed set, as follows:

- Group the cards by artist in a run of collector numbers. Find each scene's layout by matching the art along the card edges.
- Check the composed picture by eye before writing the file. So far every scene is in collector-number reading order.
- Take each name from the official product or announcement names, as printed.

Sets with scenes so far: ltr, hob, hoc, ltc.

## 6. Decks

- Two-color sample decks: `tools/build_set_decks.py "$CARDS" sets/<code>.json [printings file]` writes `decks/<code>-<pair>.txt`.
- Commander precons: the official decklists as `decks/<code>-<name>.txt`, with the "official decklist" header line.

## 7. Draft ratings

For a set that can be drafted, run `tools/draft_ratings.py <code> [format]` (format default PremierDraft). It downloads the set's public
game and draft datasets into `~/.cache/arcanum/17lands` and writes `ratings/<code>.json`, which ships with the module. A set without
public datasets fails the download and gets no file; the computer drafters then use the engine's own ratings. Commit the file with the set.

## 8. Career

Add the set to `career/career.json`: `sets` and `featured` (booster shelf), the sample decks to `starter` and `precons`, and commander
precons to `precons` with a price and to the commander night's `decks`.

## 9. Soak

```sh
ARCANUM_MODULE_PATH=$PWD ARCANUM_CARD_FILE="$CARDS" ARCANUM_SMOKE_SET=<code> ARCANUM_SMOKE_GAMES=500 \
  dotnet test "$ENGINE/tests/Arcanum.Data.Tests" --filter SetGamesPlayWithoutErrorsWhenProvided --logger "console;verbosity=detailed"
```

`ARCANUM_MODULE_PATH` must be absolute. Fix every error it reports; its list of cards never cast shows what the decks never reach.

## 10. Release

Bump the module version (and the engine API version when the module needs new engine features), then follow the release workflow.
