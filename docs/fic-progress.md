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

## Still to do (set)

- Not yet run in real games. The soak (four-player commander games with the fic decks) is the next check for all new scripts.
- `sets/fic.json`: the card list, like `sets/hoc.json`.
- The four precon decklists (Limit Break, Counter Blitz, Revival Trance, Scions & Spellcraft) as `decks/fic-*.txt`, from the public
  deck files of the open card-data project. Four Collector's Edition versions also exist (same lists, other printings). Decide whether
  they are sold separately.
- Career store: price like the other full commander precons, 45.00. Then commander night.
- The FIN Collector Booster, which holds fic cards, after fic is complete.
- Module manifest and apiVersion bump, and the release, only when asked.

## Notes for whoever continues

- The script parser silently ignores unknown keys. Check new scripts against the parser (a key checker), and read each card's text.
- Follow [set-workflow.md](set-workflow.md): support dump, triage, scripts, soak.
