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

## Game content

Star Wars Rebellion and its original assets belong to their respective rights holders. They are not supplied by this project. Local extraction is for inspecting the user's own installation; do not commit or redistribute extracted content in this repository.
