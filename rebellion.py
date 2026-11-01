"""Inspect, preview, apply, and restore data patches for Star Wars Rebellion."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SCHEMAS = json.loads((ROOT / "schemas.json").read_text(encoding="utf-8"))["tables"]
DEFAULT_PRESET = ROOT / "presets" / "fleet-roles-v0.1.json"
# Deliberately restrict writes to understood fields for this prototype.
EDITABLE = {"MaintenanceCost", "RefinedMaterialCost", "Hull", "ShieldStrength",
            "FighterCapacity", "TroopCapacity"}


class PatchError(ValueError):
    """An unsupported input or unsafe operation; no override flag is provided."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes, table: str) -> list[dict]:
    schema = SCHEMAS[table]
    if len(data) < 16:
        raise PatchError(f"{table}: truncated header")
    version, count, _, _ = struct.unpack_from("<4I", data)
    if version != 1 or count == 0 or len(data) != 16 + count * schema["record_size"]:
        raise PatchError(f"{table}: unsupported record count or file length")
    records = []
    for i in range(count):
        base = 16 + i * schema["record_size"]
        record = {field["name"]: struct.unpack_from(
            "<I" if field["type"] == "uint" else "<H", data, base + field["offset"])[0]
            for field in schema["fields"]}
        if record["Field2_1"] != 1 or record["Field7_2"] != 2:
            raise PatchError(f"{table}: invalid record markers at row {i}")
        records.append(record)
    if len({r["Id"] for r in records}) != count:
        raise PatchError(f"{table}: duplicate entity IDs")
    return records


def table_path(game: Path, filename: str) -> Path:
    # Accept only known basenames, never paths supplied by a preset/backup.
    if filename not in {f"{name}.DAT" for name in SCHEMAS}:
        raise PatchError(f"Unsupported table: {filename}")
    game = game.resolve(strict=True)
    folder = (game / "GData").resolve(strict=True)
    target = (folder / filename).resolve(strict=True)
    if folder.parent != game or target.parent != folder:
        raise PatchError("Game data must not redirect outside its game directory")
    return target


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PatchError(f"{path.name}: expected a JSON object")
    return value


def valid_hash(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def plan(game: Path, preset_path: Path) -> tuple[dict, list[dict]]:
    preset = load_json(preset_path)
    if preset.get("format_version") != 1 or not isinstance(preset.get("id"), str):
        raise PatchError("Unsupported preset format")
    tables = preset.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise PatchError("Preset must contain tables")
    result = []
    for filename, spec in tables.items():
        path = table_path(game, filename)
        before = path.read_bytes()
        if not valid_hash(spec.get("sha256")) or digest(before) != spec["sha256"]:
            raise PatchError(f"{filename}: original checksum differs. Use an unmodified supported copy; do not force it.")
        table = filename[:-4]
        records = decode(before, table)
        fields = {f["name"]: f for f in SCHEMAS[table]["fields"]}
        ids = {r["Id"]: i for i, r in enumerate(records)}
        after = bytearray(before)
        seen = set()
        changes = spec.get("changes")
        if not isinstance(changes, list) or not changes:
            raise PatchError(f"{filename}: empty changes")
        for change in changes:
            entity, name = change["id"], change["field"]
            if type(entity) is not int or entity not in ids:
                raise PatchError(f"{filename}: unknown entity ID {entity}")
            if name not in fields or name not in EDITABLE:
                raise PatchError(f"{filename}: field {name} is not writable")
            key = (entity, name)
            if key in seen:
                raise PatchError(f"{filename}: duplicate change for {key}")
            seen.add(key)
            field = fields[name]
            limit = 2 ** (32 if field["type"] == "uint" else 16)
            old, new = change["before"], change["after"]
            if any(type(v) is not int or not 0 <= v < limit for v in (old, new)) or old == new:
                raise PatchError(f"{filename}: invalid values for {key}")
            index = ids[entity]
            if records[index][name] != old:
                raise PatchError(f"{filename}: expected value differs for {key}")
            offset = 16 + index * SCHEMAS[table]["record_size"] + field["offset"]
            struct.pack_into("<I" if field["type"] == "uint" else "<H", after, offset, new)
        decode(bytes(after), table)
        result.append({"name": filename, "path": path, "before": before,
                       "after": bytes(after), "changes": changes})
    return preset, result


def atomic_write(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".rebellion-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def commit_files(entries: list[dict]) -> None:
    # Recheck the entire set just before writing. Keep the game closed throughout.
    for entry in entries:
        if entry["path"].read_bytes() != entry["before"]:
            raise PatchError(f"{entry['name']}: changed since validation")
    written = []
    try:
        for entry in entries:
            if entry["before"] == entry["after"]:
                continue
            atomic_write(entry["path"], entry["after"])
            written.append(entry)
            if entry["path"].read_bytes() != entry["after"]:
                raise OSError(f"{entry['name']}: verification failed")
    except BaseException as cause:
        rollback_errors = []
        for entry in reversed(written):
            try:
                atomic_write(entry["path"], entry["before"])
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise PatchError("Write failed and rollback was incomplete. Preserve the backup and run restore. "
                             + "; ".join(rollback_errors)) from cause
        raise


def apply(game: Path, preset_path: Path, backup: Path) -> dict:
    preset, entries = plan(game, preset_path)
    game, backup = game.resolve(), backup.resolve()
    if backup == game or game in backup.parents:
        raise PatchError("Backup must be outside the game directory")
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"format_version": 1, "preset": preset["id"], "files": {}}
    # All originals and a durable manifest exist before any game file is replaced.
    for entry in entries:
        with (backup / entry["name"]).open("xb") as stream:
            stream.write(entry["before"])
            stream.flush()
            os.fsync(stream.fileno())
        if (backup / entry["name"]).read_bytes() != entry["before"]:
            raise PatchError("Backup verification failed")
        manifest["files"][entry["name"]] = {
            "original_sha256": digest(entry["before"]),
            "patched_sha256": digest(entry["after"])}
    with (backup / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    commit_files(entries)
    return manifest


def restore(game: Path, backup: Path) -> None:
    backup = backup.resolve(strict=True)
    manifest = load_json(backup / "manifest.json")
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise PatchError("Unsupported backup manifest")
    entries = []
    for filename, hashes in manifest["files"].items():
        path = table_path(game, filename)
        saved = (backup / filename).resolve(strict=True)
        if saved.parent != backup:
            raise PatchError("Backup file redirects outside the backup directory")
        original = saved.read_bytes()
        if not all(valid_hash(hashes.get(k)) for k in ("original_sha256", "patched_sha256")):
            raise PatchError("Invalid backup checksums")
        if digest(original) != hashes["original_sha256"]:
            raise PatchError(f"{filename}: backup checksum differs")
        current = path.read_bytes()
        if digest(current) not in (hashes["original_sha256"], hashes["patched_sha256"]):
            raise PatchError(f"{filename}: changed after patching; refusing to overwrite later edits")
        decode(original, filename[:-4])
        entries.append({"name": filename, "path": path, "before": current, "after": original})
    commit_files(entries)


def inspect(game: Path, with_names: bool = False) -> dict:
    tables = {name: decode(table_path(game, f"{name}.DAT").read_bytes(), name) for name in SCHEMAS}
    if not with_names:
        return tables
    if sys.platform != "win32":
        raise PatchError("Name extraction needs Windows; omit --names to inspect numeric data")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel.LoadLibraryExW.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
    user.LoadStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
    # Read strings as resources only, without executing DLL initialization code.
    handle = kernel.LoadLibraryExW(str(game.resolve() / "TEXTSTRA.DLL"), None, 2)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for records in tables.values():
            for record in records:
                buffer = ctypes.create_unicode_buffer(2048)
                if not user.LoadStringW(handle, record["TextStraDllId"], buffer, len(buffer)):
                    raise PatchError(f"Missing name for entity {record['Id']}")
                record["Name"] = buffer.value
    finally:
        kernel.FreeLibrary(handle)
    return tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "plan", "apply", "restore"):
        child = sub.add_parser(command)
        child.add_argument("--game", type=Path, required=True, help="Directory containing GData")
        if command in ("plan", "apply"):
            child.add_argument("--preset", type=Path, default=DEFAULT_PRESET)
        if command in ("apply", "restore"):
            child.add_argument("--backup", type=Path, required=True)
        if command == "inspect":
            child.add_argument("--names", action="store_true", help="Read names from your DLL (Windows)")
            child.add_argument("--output", type=Path, help="Create a new local JSON export; never overwrites")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            tables = inspect(args.game, args.names)
            for name, records in tables.items():
                print(f"{name}: {len(records)} records")
            if args.output:
                with args.output.open("x", encoding="utf-8") as stream:
                    json.dump(tables, stream, indent=2)
                print(f"Local export: {args.output}")
        elif args.command == "plan":
            preset, entries = plan(args.game, args.preset)
            print(f"{preset['id']} (experimental; gameplay balance not yet validated)")
            for entry in entries:
                for change in entry["changes"]:
                    print(f"{change.get('name', change['id'])}: {change['field']} {change['before']} -> {change['after']}")
            print(f"{sum(len(e['changes']) for e in entries)} changes across {len(entries)} files. No files written.")
        elif args.command == "apply":
            manifest = apply(args.game, args.preset, args.backup)
            print(f"Applied {manifest['preset']}; verified {len(manifest['files'])} files. Backup: {args.backup}")
        else:
            restore(args.game, args.backup)
            print("Original files restored and verified. Backup retained.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
