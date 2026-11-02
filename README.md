# Rebellion Overhaul

[![Tests](https://github.com/trafaelosborn/rebellion-overhaul/actions/workflows/tests.yml/badge.svg)](https://github.com/trafaelosborn/rebellion-overhaul/actions/workflows/tests.yml)

Live skills and conditional odds inside the mission setup screen, a mission-planning companion, and an experimental fleet-balance toolkit for **Star Wars Rebellion (1998)**.

Inspect the original data, preview every change, apply a checksum-verified patch, and restore the exact original files. Python 3.11+; no third-party Python dependencies.

**Status: prototype.** The fleet preset launches in the supported game, and live character readings have been compared with its Status screen. Automated tests cover the patcher and mission calculations. Campaign balance, AI behavior, tactical combat, and save compatibility remain unverified.

## In-game mission panel

Start Rebellion and load a campaign, then double-click **`Launch-Ingame-Mission-Panel.cmd`** (Windows, 64-bit Python 3.11+). Or run:

```powershell
python mission_inline.py
```

Open **Create Mission** normally. The panel appears inside that window and follows the actual mission, agents, and decoys. It shows current relevant skills and the installed table's conditional resolution-roll percentage. Click **< / >** to inspect each member. Own-system support and Stormtrooper counts are read automatically; unavailable target information remains unknown.

On the Mission tab, it replaces the mission illustration while keeping the mission selector and target visible. On Agents/Decoys it fits below compact lists (up to two members per column). Larger assignment lists retain their original layout; use the Mission tab to inspect their members. The display refreshes approximately every 0.8 seconds.

Click the panel's small **x**, run **`Stop-Ingame-Mission-Panel.cmd`**, or run `python mission_inline.py --stop` to remove it. Launch it again for the next game session. The helper creates a temporary Windows child control and temporarily shortens compact assignment lists; it does not patch the executable or write game memory/files/saves. Normal shutdown restores list sizes. If the helper is forcibly terminated, close and reopen Create Mission to restore the layout.

**The percentage is the individual agent's resolution roll, not overall mission success.** Interception, capture, travel, decoys, and final effects require additional rules. Special forces, Jedi training, and reconnaissance do not yet have readings; research shows capabilities without percentages. The panel supports one checksum-pinned English executable, tested in the original 640 × 480 fullscreen game. It is an experimental helper that must stay running, not a permanent game patch.

See [mission rules, compatibility, and evidence](docs/MISSION-PLANNER.md). The fleet preset is optional.

## Separate mission planner

Start Rebellion and load a campaign, then double-click **`Launch-Mission-Planner.cmd`** (Windows, 64-bit Python 3.11+ with Tkinter). Or run:

```powershell
python mission_planner.py
```

The companion detects the running installation and your faction, reads current effective skills, and refreshes the roster. Choose a mission to rank characters by its relevant skill, then assign proposed agents and decoys. It reads your installed probability tables to show each agent's conditional resolution-roll chance. Unknown target information stays unknown; enter support or target Combat only when you know it.

This companion remains available for browsing and comparing the full roster and entering known target assumptions manually. Its proposed team is independent of the game's mission dialog. Issue orders in Rebellion.

Live mode supports one checksum-pinned original English executable. It requests read-only process access and does not modify memory, game files, or saves. No administrator rights should be necessary when both applications run as the same user. The window needs at least 980 × 680 of usable display space; it prefers a larger monitor when fullscreen Rebellion changes the primary screen to 640 × 480. On a single monitor, use a windowed game configuration with enough desktop space.

See [mission rules, compatibility, and evidence](docs/MISSION-PLANNER.md). The fleet preset is optional; the planner also works with the supported original executable and unmodified ship tables.

## What is here

- A reader for seven tables: capital ships, fighters, major/minor characters, troops, manufacturing facilities, and production facilities.
- A JSON preset with 20 edits across 15 ship/fighter types. Each edit records its original value, replacement, and design reason.
- Read-only previews; whole-file SHA-256 checks before patching; backups; checked restoration.
- A native mission-setup panel that follows the game's selected mission, team, and roles, plus a separate roster planner.
- Live player skills and table-based per-agent roll calculations for ten mission types, with unknown inputs kept explicit.
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

The data reader, patcher, and mission calculation logic are portable Python. Live process reading and name extraction from `TEXTSTRA.DLL` require Windows. Cross-platform CI verifies synthetic inputs; it does not demonstrate game compatibility on those operating systems.

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

Engine behavior and multiplayer/save compatibility are untested. There are no new units, factions, graphics, mission rules, or AI routines in this prototype. The mission planner explains existing rules and skills. Before applying balance changes to a campaign you want to preserve, complete the [playtest checklist](docs/PLAYTESTING.md).

## Development

```powershell
python -m unittest discover -s tests -v
```

The tests cover patch safety, exact restoration, malformed binary input, mission formulas, step-table boundaries, missing target information, character visibility, and current-skill decoding. All fixtures use synthetic values. See [validation notes](docs/VALIDATION.md).

Presets are JSON. The writer currently permits only cost, hull, shield, and capacity fields. IDs, family markers, unknown fields, and other structural data cannot be changed. Use `--preset path/to/preset.json` with `plan` or `apply` for your own preset; restoration uses the saved manifest.

## Credits and scope

Binary field layout names, types, and ordering are based on community research implemented in [MetasharpNet/StarWarsRebellionEditor.NET](https://github.com/MetasharpNet/StarWarsRebellionEditor.NET). The exact source revision and relevant files are recorded in [CREDITS.md](CREDITS.md) and `schemas.json`. This project builds on that work; it does not claim to have independently discovered those formats.

The original code in this repository is available under the [MIT License](LICENSE). The license does not grant rights to the original game's assets or third-party projects. This is an independent fan project, unaffiliated with the game's rights holders.
