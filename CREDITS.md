# Credits and provenance

## Binary format research

[MetasharpNet/StarWarsRebellionEditor.NET](https://github.com/MetasharpNet/StarWarsRebellionEditor.NET) documents Rebellion's data structures in its editor implementation.

The field layout metadata in `schemas.json` records the field names, integer widths, order, and offsets from these files at commit [`0ecdef839ecae4f9f114229d3017f077cd8aa8e3`](https://github.com/MetasharpNet/StarWarsRebellionEditor.NET/tree/0ecdef839ecae4f9f114229d3017f077cd8aa8e3/SwRebellionEditor/GData):

- `CAPSHPSD.cs`: capital ships
- `FIGHTSD.cs`: fighters
- `MJCHARSD.cs`: major characters
- `MNCHARSD.cs`: minor characters
- `MANFACSD.cs`: manufacturing facilities
- `PROFACSD.cs`: production facilities
- `TROOPSD.cs`: troops

The source editor's `DatFile.cs` supplies context for binary field serialization. The Python reader, patch planner, backup/restore implementation, tests, and experimental balance choices were written for this project. No upstream editor source files or binaries are bundled.

The [SW:Rebellion community](https://swrebellion.net/) and the original [RebED](https://swrebellion.net/rebed/) tooling kept this game's modding ecosystem alive.

## Mission and runtime research

[Tom di Mino's Open Rebellion](https://github.com/tdimino/open-rebellion), revision [`e8ae0457e7fac9276e2212e9c9c9521a32603744`](https://github.com/tdimino/open-rebellion/tree/e8ae0457e7fac9276e2212e9c9c9521a32603744/ghidra/notes), documents the original executable's runtime character fields, ownership/views, mission phases, and probability-table lookup. The mission planner's implementation uses those documented facts and local read-only checks of the matching executable. Specific sources and validation limits are listed in [MISSION-PLANNER.md](docs/MISSION-PLANNER.md). No upstream implementation or decompiler listing is bundled.

The embedded panel also uses that project's mission-dialog control layout, member-list traversal, and system-context research. Its Windows child-control implementation is original Python/ctypes code using Microsoft's [CreateWindowExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindowexw) and [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos) APIs. No original artwork is distributed with the panel.

## Game content

Star Wars Rebellion and its original assets belong to their respective rights holders. They are not supplied by this project. Local extraction is for inspecting the user's own installation; do not commit or redistribute extracted content in this repository.
