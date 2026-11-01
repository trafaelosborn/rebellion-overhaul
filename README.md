# Rebellion Overhaul

[![Tests](https://github.com/trafaelosborn/rebellion-overhaul/actions/workflows/tests.yml/badge.svg)](https://github.com/trafaelosborn/rebellion-overhaul/actions/workflows/tests.yml)

A reproducible modding toolkit and experimental fleet-balance preset for **Star Wars Rebellion (1998)**.

Inspect the original data, preview every change, apply a checksum-verified patch, and restore the exact original files. Python 3.11+; no third-party Python dependencies.

**Status: prototype.** The tooling has automated safety tests. The first preset has been applied to local copies of supported game tables, read back, and restored byte for byte. It has **not** been playtested in the game: campaign balance, AI behavior, tactical combat, and save compatibility remain unverified. This is a starting point for experiments, not a finished overhaul.

## What is here

- A reader for seven tables: capital ships, fighters, major/minor characters, troops, manufacturing facilities, and production facilities.
- A JSON preset with 20 edits across 15 ship/fighter types. Each edit records its original value, replacement, and design reason.
- Read-only previews; whole-file SHA-256 checks before patching; backups; checked restoration.
- Synthetic test fixtures and Windows/Linux CI. Tests do not need the game.

This repository contains tools and modification instructions. **No game executables, DLLs, original data tables, artwork, audio, or saves are included.** You supply your own installed copy.

## First experiment: fleet roles

The design hypothesis is that cheaper escorts and carrier support encourage mixed fleets, while stronger Imperial destroyer hulls justify higher maintenance. Mon Calamari shields receive a corresponding specialist upgrade. These are hypotheses to test, not measured balance improvements.

| Example | Original | Prototype |
| --- | ---: | ---: |
| Corellian Corvette maintenance | 23 | 18 |
| Alliance Escort Carrier maintenance | 29 | 25 |
| Mon Calamari Cruiser shields / maintenance | 300 / 70 | 400 / 74 |
| Imperial Star Destroyer hull / maintenance | 2,750 / 71 | 3,100 / 80 |
| B-wing maintenance | 8 | 6 |
| TIE Fighter maintenance | 3 | 2 |

See [all 20 changes and their rationale](docs/BALANCE.md). Only `CAPSHPSD.DAT` and `FIGHTSD.DAT` are edited by this preset. Character, research, map, and production-facility changes are future work.

## Compatibility

The included preset is validated against the two specific original English Steam data files listed below. File hashes, rather than a storefront label, decide compatibility. GOG versions and other installs may match, but have not been independently tested. Modified files, including other overhauls, are refused if their hashes differ. There is no force option.

| File | Supported original SHA-256 |
| --- | --- |
| `CAPSHPSD.DAT` | `36fdaaeef4057d70e10a1593950cee5b197ce38d7d1b6a06201a74c93bf44515` |
| `FIGHTSD.DAT` | `b62598d9a35fa3fe9fb65622f2720d10e6fabba055ccba41b87bdf07895268a5` |

The reader and patcher are portable Python. Optional name extraction from `TEXTSTRA.DLL` requires Windows. Cross-platform CI verifies synthetic files; it does not demonstrate game compatibility on those operating systems.

## Try it

Download or clone this repository. Run commands from its directory. Find the game installation using your launcher and substitute that directory for the example below. It must contain `GData`. Keep the game and other editors closed while applying or restoring. Begin with a disposable game copy and a fresh test campaign.

PowerShell examples:

```powershell
$gamePath = 'C:\Games\Star Wars - Rebellion'

# Read table counts without writing anything.
python rebellion.py inspect --game "$gamePath"

# See every proposed change. No files are written.
python rebellion.py plan --game "$gamePath"

# Apply only after reviewing the preview. Use a NEW backup directory.
python rebellion.py apply --game "$gamePath" --backup '.\backups\fleet-roles-01'

# Return both tables to their exact original bytes. The backup is retained.
python rebellion.py restore --game "$gamePath" --backup '.\backups\fleet-roles-01'
```

Backups must be outside the game directory. Keep the backup folder until you have restored the game. If a file was edited again after patching, restoration stops rather than overwriting that edit. Existing backup directories are never reused. Restoring an already-restored file is safe.

To export data and names locally on Windows:

```powershell
New-Item -ItemType Directory -Force exports
python rebellion.py inspect --game "$gamePath" --names --output exports\tables.json
```

Exports are ignored by Git. The output must be a new file. Names are read as Windows resources without executing the game DLL's initialization code.

## Safety and limitations

The patcher validates the complete file set and every expected value before changing anything. It saves and verifies every original, then writes a durable manifest before patching. Each individual replacement uses a temporary file and an atomic rename, followed by read-back verification. Ordinary write failures trigger rollback of files already replaced.

Two files cannot be replaced as one filesystem transaction. A power loss, forced process termination, or failed rollback can leave a mixed state. The retained backup can restore a mixture of intact originals and expected patched files. If a file is damaged or changed to another value, restoration deliberately refuses; preserve the backup and investigate. Keep the game closed throughout the operation to avoid concurrent writes. The tool does not lock the entire installation or detect every running editor.

Engine behavior and multiplayer/save compatibility are untested. There are no new units, factions, graphics, missions, or AI routines in this prototype. Do not use it for a campaign you want to preserve before completing the [playtest checklist](docs/PLAYTESTING.md).

## Development

```powershell
python -m unittest discover -s tests -v
```

The tests cover exact restoration, checksum mismatches, interrupted multi-file writes, corrupt backups, edits made after patching, path traversal, duplicate/invalid edits, and malformed binary input. All fixtures are generated from synthetic values. See [validation notes](docs/VALIDATION.md).

Presets are JSON. The writer currently permits only cost, hull, shield, and capacity fields. IDs, family markers, unknown fields, and other structural data cannot be changed. Use `--preset path/to/preset.json` with `plan` or `apply` for your own preset; restoration uses the saved manifest.

## Credits and scope

Binary field layout names, types, and ordering are based on community research implemented in [MetasharpNet/StarWarsRebellionEditor.NET](https://github.com/MetasharpNet/StarWarsRebellionEditor.NET). The exact source revision and relevant files are recorded in [CREDITS.md](CREDITS.md) and `schemas.json`. This project builds on that work; it does not claim to have independently discovered those formats.

The original code in this repository is available under the [MIT License](LICENSE). The license does not grant rights to the original game's assets or third-party projects. This is an independent fan project, unaffiliated with the game's rights holders.
