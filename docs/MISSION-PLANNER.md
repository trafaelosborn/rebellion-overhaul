# Mission tools v0.3

The embedded panel shows current skills and conditional mission-resolution rolls inside Create Mission. The separate companion helps compare the full roster. Both explain the original mission rules without changing them.

## Embedded panel

1. Start the supported Rebellion executable and load a campaign.
2. Run `python mission_inline.py` or double-click `Launch-Ingame-Mission-Panel.cmd`.
3. Open Create Mission in the game. The helper reads the actual selected mission and both member lists; no duplicate team selection is needed.
4. Use **< / >** to cycle members. Each member is explicitly labeled agent or decoy. Mouse-wheel paging is also handled when Windows delivers wheel events to the panel.
5. Close the helper using its small **x**, `Stop-Ingame-Mission-Panel.cmd`, or `python mission_inline.py --stop`.

The Mission tab's illustration becomes the skills panel; the mission selector, target, and order buttons remain available. On Agents/Decoys, lists with at most two members each are temporarily shortened to make room below. Larger teams retain the full original assignment lists and can inspect their members on the Mission tab. The game remains authoritative for mission eligibility and orders.

Refresh is approximately every 0.8 seconds, so tab, mission, and role changes may take a moment to appear. Invalid or changing readings remove the panel until a valid setup is available. Closing Create Mission removes its child panel; reopening it attaches a new one. Only one helper instance is allowed. It exits when the game closes; start it again for a new game process.

Support and usable Imperial Stormtrooper regiment counts are read only from **your own systems in your faction's view**. Enemy/neutral-system context and target-character Combat are left unknown. Neither unknown support nor unknown defenders is assumed to be zero. Missions requiring missing inputs show no percentage. Special forces are retained in the member selector but have no skill/odds reading. Jedi training and reconnaissance are unsupported. The helper never starts a mission or changes a member's role.

This is a Windows child window parented to the game's real mission dialog, owned by the Python helper process. It is not a second planner window or a persistent executable patch. It uses normal Windows window-position operations for its panel and compact lists, with parent, class, control-ID, and process checks. Normal shutdown restores list dimensions. Forced termination cannot run cleanup: close and reopen Create Mission if the lists remain shortened. No game files, save data, process memory, DLL injection, or window-procedure hooks are involved.

It has been visually tested in the original 640 × 480 fullscreen game on Windows. Unlike the separate companion, it does not require space on another monitor. Other renderers, DPI configurations, executable builds, and long campaigns need further validation.

The helper observes left-button state to support the fullscreen game's captured mouse input. It acts only on a fresh press over its own visible panel while the game is the foreground window, and ignores covered panels, other apps, and drags that began elsewhere. It does not suppress or inject input or install a global mouse hook.

## Separate companion

1. Start the supported Rebellion executable and load a campaign.
2. Run `python mission_planner.py` or double-click `Launch-Mission-Planner.cmd`.
3. Choose the mission in the companion. The roster ranks characters by current relevant skill, including effective bonuses already computed by the game.
4. For missions needing target information, enter only known values. Support is **support for your faction**, from 0 to 100; Stormtroopers is the number of Stormtrooper regiments, not generic garrison strength. Target Combat is the target character's effective Combat rating. A blank means unknown, not zero.
5. Select characters (Ctrl-click for several), then **+ Agent** or **+ Decoy**. A character can occupy only one proposed role. Mixed locations and unavailable members produce a warning.
6. Issue the actual mission order in Rebellion. Selections in this window do not send commands to the game.

Auto refresh runs approximately every 2.5 seconds. Pause the game when comparing a stable setup. A failed refresh clears displayed readings and the proposed team; reconnect after loading. A detected campaign change also clears target inputs. There is no saved plan or telemetry.

The planner reads only recruited, existing, uncaptured characters owned by the local player's side, from that side's view. It does not display the enemy roster, unrecruited characters, prisoners, loyalty, hidden Force potential, or hidden defenders. Special-force units are not yet supported. The original game's availability checks remain authoritative.

The window requires 980 × 680 usable pixels. When Rebellion puts the primary display into 640 × 480, the planner chooses a larger available monitor. A single-display setup needs a windowed game configuration and enough desktop space. `Keep on top` is optional; it does not inject an overlay into DirectDraw.

For a console-only connection check:

```powershell
python mission_planner.py --snapshot
```

An optional `--game 'C:\Games\Star Wars - Rebellion'` checks that the running game comes from the intended installation. Otherwise the process image path supplies the installation. Start exactly one game process. Use the same Windows user for both applications.

## What a percentage means

The original mission system rolls separately for each eligible **team agent** at resolution. Decoys are a separate list and do not take those success rolls. The value shown is the probability of that individual check, **conditional on the agent reaching resolution**. It is neither the probability of surviving the mission nor a combined team chance. Repeating missions can attempt multiple resolutions.

The `IntTableEntry` format contains signed threshold/value pairs. The lookup uses the greatest threshold less than or equal to the score, clamped at both ends. It does **not** interpolate. A uniform integer roll from 0 through 99 succeeds when it is less than the looked-up percentage.

All table values are loaded from the user's local installation. No vanilla probability arrays are distributed. Restart the game and reconnect after changing probability tables: editing disk files does not necessarily change the tables already loaded by a running game.

| Mission | Resolution score | Local table |
| --- | --- | --- |
| Espionage | Espionage | ESPIMSTB |
| Sabotage | floor((Espionage + Combat) / 2) | SBTGMSTB |
| Death Star sabotage | floor((Espionage + Combat) / 2) | DSSBMSTB |
| Rescue | Combat | RESCMSTB |
| Abduction | Combat − target Combat | ABDCMSTB |
| Assassination | Combat − target Combat | ASSNMSTB |
| Diplomacy | Diplomacy − own support + Stormtrooper regiments | DIPLMSTB |
| Recruitment | Leadership − own support; major characters only | RCRTMSTB |
| Incite uprising | Leadership − own support − Stormtrooper regiments | INCTMSTB |
| Subdue uprising | Leadership − own support + Stormtrooper regiments | SUBDMSTB |

Research displays the relevant current capability, with no percentage. Decoys display current Espionage, with no percentage. No total mission, detection, capture, escape, travel-time, or aggregate-team probability is implemented. The companion's target fields are manual assumptions; the embedded panel reads only the known own-system context described above. Final mission effects and ordering can matter even after a successful agent roll.

## Live compatibility

The adapter rejects an unrecognized executable. The tested original English Steam binary has SHA-256:

```text
b3fe3997cab9a6e96403d638875dcba25484e4d8601751afec748471ac0ed6ab
```

This is an exact build match, not a promise that all Steam or GOG distributions work. Modified executables, anniversary patches, other languages, Wine, and 32-bit Python have not been validated. Editing supported DAT values does not change the executable hash, though unsupported structural changes can still prevent connection.

The adapter uses `OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)`. It does not ask for write, operation, create-thread, debugging, or suspension permissions. Name DLLs are loaded with `LOAD_LIBRARY_AS_DATAFILE`; their initialization code is not executed. It writes no game files or process memory.

The scan is bounded to readable private regions below the game's 2 GiB address limit and at most 512 MiB per refresh. Candidates must match a known character vtable, catalog ID/family, the player's ownership/view, created/completed/existing flags, a reciprocal view pointer, and class identity. It rereads accepted objects and checks session identity to catch some concurrent changes. This is **not an atomic game snapshot**. Pause the game for a stable comparison; memory access errors clear the UI rather than presenting stale odds as live.

## Research and validation

Field offsets and mission semantics are based on [Open Rebellion's research at e8ae0457](https://github.com/tdimino/open-rebellion/tree/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes), checked against the user's matching binary. This project implements its own Python reader and calculation code; it does not ship the original executable, decompiler output, upstream source, or game tables.

Relevant primary notes and routines:

- [Status window](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/status-window.md): effective Diplomacy `+0x7c`, Espionage `+0x7e`, Combat `+0x86`, Leadership `+0x88`; research capabilities `+0x80/82/84`.
- [Decoy roll and phase-10 resolution](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/decoy-roll.md): per-agent mission rolls and separate decoy lists; `FUN_00592f50` and mission wrappers.
- [Probability tables](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/uprising-incident.md): score formulas, support/Stormtrooper meanings, and step lookup `FUN_00595090`.
- [Side numbering](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/side-numbering.md), [object flags](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/object-state-flags.md), and [character roster](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/character-roster.md): view/ownership filtering, existence, classes, and recruitment eligibility.
- [Mission dialog](https://github.com/tdimino/open-rebellion/blob/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes/mission-dialog.md): native pages, controls, selected mission, and agent/decoy lists (`FUN_0046a750`, `FUN_0046a9c0`, `FUN_0046c3c0`). Own support and Stormtrooper counts use the meanings verified in `FUN_00507270` and `FUN_005091f0`. Native list traversal was checked against `FUN_005f5060`.

The embedded reader validates dialog/order vtables and side identity, limits intrusive-list traversal, rejects duplicate members, and rereads the selection after collecting context and skills. Cached candidates must still name a live game-owned mission HWND, so freed dialog memory cannot hide a newly opened setup. These checks reduce stale readings but do not make a running campaign atomic.

Local checks compared the four effective skills with the original game's Status screen and identified eight recruited Empire characters in a fresh campaign. Tests exercise synthetic memory records and tables, including unknown target values and threshold boundaries. These checks validate the displayed inputs and implemented conditional calculations; they are **not** a statistical measurement of complete mission outcomes. See [the validation record](VALIDATION.md).

## Further work

Support special forces and more known-target inputs, validate the defender/decoy/capture sequence, and test larger campaigns and additional display configurations. Complete mission-outcome odds remain unimplemented.
