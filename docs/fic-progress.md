# fic (commander decks of the heroes set): progress

Status 2026-10-17: all 339 cards are supported. Work continues on branch `fic-wip` of this repository and branch `fic` of the engine
repository.

## Done

- 339 cards in the set. All 339 are fully supported by the support dump (SupportDump). The three adventure cards (Hypnotic Sprite and
  Murderous Rider among them) appear under their front-face name, so a naive count by face name may list them.
- About 170 new card scripts, plus fixes to the 52 earlier work-in-progress scripts. Several of those were silently wrong, because the
  script parser ignores keys it doesn't know. The fixed cards are Cait Sith, Cyan, Archfiend of Depravity, Collective Effort, Banon,
  Alisaie, Blue Mage's Cane, Celes, Dig Through Time, Archaeomancer's Map, Conqueror's Flail and Edgar.
- Engine (branch `fic` of the engine repository):
  - New keywords: Intimidate, Melee, Evolve, Training, Convoke, Unearth, Rebound, Blitz, Foretell.
  - New keyword actions: Support, Adapt, Monstrosity, Explore, Connive.
  - Shield counters, for damage prevention and destroy-by-effect only.
  - The new script vocabulary is documented in the engine docs (`card-scripts.md`, "Commander decks of the heroes set"; `engine-map.md`).
- Engine tests: 861 pass. Data tests: 236 pass.
- `sets/fic.json`: the 339 cards, released 2025-06-13.
- Eight precon decklists from the public deck files of the open card-data project. Every printing was checked against the card data.
  - `decks/fic-counter-blitz`, `fic-limit-break`, `fic-revival-trance` and `fic-scions-spellcraft`: the commander and the second
    face commander are traditional foils.
  - `decks/fic-*-collectors-edition` (the same four): the same lists, every card a surge foil, a few printings from FIN.
- Career store (`career/career.json`): the regular decks at 45.00, the Collector's Editions at 95.00 (priced by the real ones' ratio,
  $149.99 against $69.99). The four regular decks are in commander night.
- The FIN Collector Booster in `sets/fin.json` (`boosters.collector`): four variants from the published collation sheet weights, 41
  sheets, including the fic Booster Fun and surge foil sheets and the fca Through the Ages sheet. 2000 test packs open complete, with
  only supported cards.
- Commander soak of the fic decks (60 four-player games): after the two fixes below, all 60 finish with no errors. It found two engine bugs, both fixed:
  - a crash while listing castable cards with a graveyard Adventure permission;
  - tiered spells offered as castable when no mode with legal targets could be paid for.

## Still to do (set)

- Module manifest and apiVersion bump, merging `fic-wip` and the engine's `fic`, and the release, only when asked.

## Notes for whoever continues

- The script parser silently ignores unknown keys. Check new scripts against the parser (a key checker), and read each card's text.
- Follow [set-workflow.md](set-workflow.md): support dump, triage, scripts, soak.
