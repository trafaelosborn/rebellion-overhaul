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

## Not yet verified

- Launching the game with the patched tables
- Campaign initialization, progression, and AI behavior
- Tactical combat and automatic battle resolution
- Save/load and multiplayer compatibility
- Long-term faction balance
- Other distributions or already-modded installations

These limits are intentional release-status disclosures. File-level validation alone cannot answer gameplay questions.
