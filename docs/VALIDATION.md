# Validation record

## Initial prototype — 2026-10-31

Local environment: Windows, Python 3.14.

- 16 automated tests passed using synthetic data only.
- Read seven tables from an original English Steam installation: 30 capital ships, 8 fighters, 6 major characters, 54 minor characters, 10 troop types, 6 manufacturing facilities, and 2 production facilities.
- Applied the shipped preset to disposable copies of the original game data.
- Read back and verified all 20 changed fields across 15 entities in two files.
- Confirmed the 23 changed bytes were all inside the intended field ranges. Every other byte was preserved.
- Confirmed all unrelated files remained unchanged.
- Restored and compared all 55 copied data files against the originals byte for byte.
- Confirmed the installed game's data files still matched the untouched baseline.

Original game files and the local integration fixture are not included in this repository. CI uses synthetic fixtures and reports its current outcome in the repository's Actions tab.

## Mission planner and launch check — 2026-11-01

- The installed fleet preset launched and a fresh Empire campaign initialized. This is a smoke check, not a balance assessment.
- 31 automated tests passed locally on Windows/Python 3.14. All committed fixtures are synthetic.
- Confirmed the supported executable hash and effective-skill getter addresses against the installed binary.
- Read eight existing, recruited, uncaptured Empire characters from the running campaign. Unrecruited and other-side views were excluded.
- Compared Vader's live values with the game's Character Status screen: Diplomacy 88, Espionage 110, Combat 220, Leadership 150. All four matched.
- Confirmed character locations against the Personnel Finder, including generated ship names.
- Loaded all ten local mission probability tables. Checked step thresholds and per-agent calculations; no interpolation or fallback formula is used.
- Opened and visually checked the companion, live refresh, character selection, and agent assignment. It moves onto a sufficiently large available monitor when fullscreen Rebellion reduces the primary display resolution.
- No process writes, save changes, or game-table edits are performed by the planner.

The companion is a separate UI. Conditional-roll formulas are grounded in the cited reverse engineering, not calibrated by repeated complete missions.

## Embedded mission panel — 2026-11-01

- 49 synthetic tests passed locally on Windows/Python 3.14, including native-list traversal, changing selections, stale dialog handles, campaign changes, role changes, own-system visibility, and pointer focus/occlusion guards.
- Created a native Windows child control inside the original Create Mission dialog and visually verified it in 640 × 480 fullscreen play. The Mission tab retains its mission selector and target; the Agents/Decoys tab displays the panel below compact assignment lists.
- Read the actual selected Recruitment mission, its agent, Coruscant's own-faction support, and six usable Stormtrooper regiments from the fresh Empire test campaign.
- Displayed the Emperor's current Leadership 150, score 50, and the installed table's 45% conditional recruitment roll. Moving him to Decoys changed the panel to Espionage 50 and no mission-success percentage; moving him back restored the agent reading. No mission was submitted for this check.
- Checked switching between both native tabs and opening/closing the native mission selector while the panel was present.
- Checked stop/restart and the panel's close button. Normal shutdown removed the child control and restored the full original assignment lists.
- Member paging has synthetic coverage; larger live teams, their layout fallback, and wheel-input delivery still need playtesting.
- The integration requests read-only process access. Its only game-window changes are temporary child controls and compact-list dimensions; it does not patch game binaries, memory, tables, or saves.

Special forces, Jedi training, reconnaissance, and overall mission-success/detection/capture odds remain unsupported. Enemy and neutral target context stays unknown. These tests do not validate long-running play, every display configuration, or every mission's complete outcome.

## Not yet verified

- Extended campaign progression and AI behavior
- Tactical combat and automatic battle resolution
- Save/load and multiplayer compatibility
- Long-term faction balance
- Other distributions or already-modded installations
- Complete mission-outcome probabilities, captured-character handling, and long-running live-reader reliability

These limits are intentional release-status disclosures. File-level validation alone cannot answer gameplay questions.
