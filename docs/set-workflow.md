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

- `tools/generate_scripts.py "$CARDS"` writes scripts for cards with fixed phrasings (`"generated": true`).
- Every other card gets a hand-written `scripts/<oracle id>.json`. Write exactly what the card does: every choice and restriction.
- A mechanic the engine lacks goes into the engine first (see `engine-map.md`), with a test, then the script uses it.
- New keywords go into `tools/engine-mechanics.txt` so the planner knows them.
- Repeat step 2 until every card of the set is supported.

## 4. The set file

`sets/<code>.json`: the card list, pack image, limited settings, and the booster sheets and slots exactly as the real product
(official collation percentages; printings by collector number, foil and showcase treatments as printed). Write down any ratio that had
to be derived from published numbers. Check the packs: every sheet non-empty, the right pack size, no unsupported card.

## 5. Decks

- Two-color sample decks: `tools/build_set_decks.py "$CARDS" sets/<code>.json [printings file]` writes `decks/<code>-<pair>.txt`.
- Commander precons: the official decklists as `decks/<code>-<name>.txt`, with the "official decklist" header line.

## 6. Career

Add the set to `career/career.json`: `sets` and `featured` (booster shelf), the sample decks to `starter` and `precons`, and commander
precons to `precons` with a price and to the commander night's `decks`.

## 7. Soak

```sh
ARCANUM_MODULE_PATH=$PWD ARCANUM_CARD_FILE="$CARDS" ARCANUM_SMOKE_SET=<code> ARCANUM_SMOKE_GAMES=500 \
  dotnet test "$ENGINE/tests/Arcanum.Data.Tests" --filter SetGamesPlayWithoutErrorsWhenProvided --logger "console;verbosity=detailed"
```

`ARCANUM_MODULE_PATH` must be absolute. Fix every error it reports; its list of cards never cast shows what the decks never reach.

## 8. Release

Bump the module version (and the engine API version when the module needs new engine features), then follow the release workflow.
