# Playtesting the fleet-roles prototype

Status: not started. Passing file checks is not evidence that a campaign is balanced.

Use a disposable game copy and fresh saves. Record the game distribution/version, preset ID, side, difficulty, galaxy size, and game day with each result. Do not upload saves or game assets to this repository.

## Smoke test

- Confirm `plan` accepts the original files, then apply with a new backup directory.
- Start a fresh campaign as each side. Confirm initialization and ordinary campaign progression work.
- Inspect edited ship/fighter statistics where the UI exposes them. Confirm cost changes appear when building units.
- Build a changed escort, carrier, fighter, and destroyer where available; observe construction and maintenance behavior.
- Enter a tactical battle with changed units and test firing, damage, retreat, and battle completion.
- Save and reload a disposable test campaign under the same preset.
- Restore, verify the file hashes, and start a separate unmodified campaign.

## Balance questions

- Are corvettes, gunships, Lancers, and escort carriers useful purchases alongside larger ships?
- Can the AI sustain its fleets with the destroyers' increased upkeep?
- Does the cheaper TIE Fighter make other fighters unattractive?
- Does the B-wing's lower maintenance overwhelm capital-ship defenses?
- Do the hull and shield changes produce reasonable tactical battle lengths?
- Do fleet choices remain interesting through research progression?
- Are differences between tactical combat and automatic resolution acceptable?

Use comparable vanilla and patched starts where possible. Random generation and AI choices make single-campaign conclusions weak. Report concrete observations, then change one related group of values at a time.

## Roadmap

1. Complete smoke tests and record outcomes before calling the preset playable.
2. Collect both Rebel and Imperial campaign feedback.
3. Revise fleet costs and durability based on evidence.
4. Investigate character roles, research pacing, and production economics separately.
5. Consider a stable release after compatibility and balance have been demonstrated.
