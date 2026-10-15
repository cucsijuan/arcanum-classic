# fic (commander decks of the heroes set): progress

Status 2026-10-15: work in progress on branch `fic-wip` of this repository and branch `fic` of the engine repository (both pushed).

## Done

- 339 cards in the set. 322 are fully supported by the support dump (SupportDump) after this work. 17 still need work (list below).
  Two adventure cards, Hypnotic Sprite and Murderous Rider, are supported; a naive count by face name may list them.
- About 170 new card scripts, plus fixes to the 52 earlier work-in-progress scripts. Several of those were silently wrong, because the
  script parser ignores keys it doesn't know. The fixed cards are Cait Sith, Cyan, Archfiend of Depravity, Collective Effort, Banon,
  Alisaie, Blue Mage's Cane, Celes, Dig Through Time, Archaeomancer's Map, Conqueror's Flail and Edgar.
- Engine (branch `fic` of the engine repository):
  - New keywords: Intimidate, Melee, Evolve, Training, Convoke, Unearth, Rebound, Blitz, Foretell.
  - New keyword actions: Support, Adapt, Monstrosity, Explore, Connive.
  - Shield counters, for damage prevention and destroy-by-effect only.
  - Many new script vocabulary items (see the engine docs once documented).
- Engine tests: 829 pass, 88 of them in `HeroesCommanderTests` for these features.

## Still to do (cards)

The 17 cards that are not yet supported:

- Duelist's Flame
- Flash Photography
- Garland Royal Kidnapper
- Gatta and Luzzu
- Gogo Mysterious Mime
- Hildibrand Manderville // Gentleman's Rise
- Inspiring Statuary
- Judgment of Alexander
- Kimahri Valiant Guardian
- Noctis Heir Apparent
- Professor Hojo
- Promise of Loyalty
- Sephiroth Fallen Hero
- Strago and Relm
- Summon: Esper Valigarmanda
- Summon: Good King Mog XII
- Urianger Augurelt

Each needs an engine feature: copy-become effects, monarch triggers, damage-prevention replacements, cast-as-adventure from the
graveyard, granting improvise, vow counters with an attack restriction, warp-strike, "cast as though it had flash if it targets",
delayed per-turn copy triggers, and linked exile play permissions.

## Still to do (set)

- Not yet run in real games. The soak (four-player commander games with the fic decks) is the next check for all new scripts.
- `sets/fic.json`: the card list, like `sets/hoc.json`.
- The four precon decklists (Limit Break, Counter Blitz, Revival Trance, Scions & Spellcraft) as `decks/fic-*.txt`, from the public
  deck files of the open card-data project. Four Collector's Edition versions also exist (same lists, other printings). Decide whether
  they are sold separately.
- Career store: price like the other full commander precons, 45.00. Then commander night.
- The FIN Collector Booster, which holds fic cards, after fic is complete.
- Engine docs (`card-scripts.md`, `engine-map.md`) for the new vocabulary.
- Module manifest and apiVersion bump, and the release, only when asked.

## Notes for whoever continues

- The script parser silently ignores unknown keys. Check new scripts against the parser (a key checker), and read each card's text.
- Follow [set-workflow.md](set-workflow.md): support dump, triage, scripts, soak.
