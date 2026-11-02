"""Read-only Windows adapter for one checksum-pinned Rebellion executable.

No injection, debugging privileges, process suspension, memory writes, or save
edits. Keep reverse-engineering details and compatibility evidence in
docs/MISSION-PLANNER.md. All offsets below are for the pinned original binary.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import struct

from mission_data import Character, PlannerError
from rebellion import decode

SUPPORTED_EXE = "b3fe3997cab9a6e96403d638875dcba25484e4d8601751afec748471ac0ed6ab"
VTABLES = {0x6657F0: 0x30, 0x6663E0: 0x31, 0x665FD8: 0x32,
           0x666F90: 0x33, 0x667628: 0x34, 0x6681D0: 0x35, 0x665BE0: 0x38}
CHARACTER_SIZE = 0xB0
READ_ACCESS = 0x0400 | 0x0010  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ


def u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def decode_character(data: bytes, catalog: dict[int, dict], side: int,
                     location: str = "Unknown", location_id: int = 0) -> Character | None:
    """Pure decoder; reject enemies, unrecruited/dead characters and other views."""
    if len(data) != CHARACTER_SIZE or side not in (1, 2):
        return None
    family = VTABLES.get(u32(data))
    ident, key, flags = u32(data, 0x18), u32(data, 0x24), u32(data, 0x50)
    record = catalog.get(ident)
    if (family is None or record is None or record["FamilyId"] != family
            or (key >> 4 & 3) != side or (key >> 6 & 3) != side
            or key & 0x100 or flags & 0x08 or flags & 0x46 != 0x46 or data[0xAC] & 1):
        return None
    stats = struct.unpack_from("<8h", data, 0x7C)
    if any(n < 0 for n in stats):
        return None
    diplomacy, espionage, ship, troop, facility, combat, leadership, _ = stats
    injury = struct.unpack_from("<h", data, 0x94)[0]
    if injury < 0:
        return None
    status = "Awaiting orders"
    if flags & 0x10:
        status = "En route"
    elif data[0xAC] & 1:
        status = "Captured"
    elif injury:
        status = "Injured"
    elif u32(data, 0x78) & 0x80:
        status = "On mission"
    return Character(ident, record["Name"], family, diplomacy, espionage, combat,
                     leadership, ship, troop, facility, location, location_id, status)


class ProcessEntry(C.Structure):
    _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
                ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD),
                ("exe", W.WCHAR * 260)]


class MemoryInfo(C.Structure):
    _fields_ = [("base", C.c_void_p), ("allocation", C.c_void_p),
                ("allocation_protect", W.DWORD), ("partition", W.WORD),
                ("size", C.c_size_t), ("state", W.DWORD), ("protect", W.DWORD),
                ("type", W.DWORD)]


def kernel_api():
    if os.name != "nt" or C.sizeof(C.c_void_p) != 8:
        raise PlannerError("Live mode requires Windows and 64-bit Python 3.11 or later.")
    k = C.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateToolhelp32Snapshot": ([W.DWORD, W.DWORD], W.HANDLE),
        "Process32FirstW": ([W.HANDLE, C.POINTER(ProcessEntry)], W.BOOL),
        "Process32NextW": ([W.HANDLE, C.POINTER(ProcessEntry)], W.BOOL),
        "OpenProcess": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
        "CloseHandle": ([W.HANDLE], W.BOOL),
        "QueryFullProcessImageNameW": ([W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
        "ReadProcessMemory": ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                               C.POINTER(C.c_size_t)], W.BOOL),
        "VirtualQueryEx": ([W.HANDLE, C.c_void_p, C.POINTER(MemoryInfo), C.c_size_t], C.c_size_t),
        "LoadLibraryExW": ([W.LPCWSTR, W.HANDLE, W.DWORD], W.HMODULE),
        "FreeLibrary": ([W.HMODULE], W.BOOL),
        "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(k, name)
        function.argtypes, function.restype = args, result
    return k


def game_processes(k) -> list[int]:
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == C.c_void_p(-1).value:
        raise PlannerError("Cannot list running processes")
    result = []
    try:
        entry = ProcessEntry()
        entry.size = C.sizeof(entry)
        more = k.Process32FirstW(snapshot, C.byref(entry))
        while more:
            if entry.exe.casefold() == "rebexe.exe":
                result.append(entry.pid)
            more = k.Process32NextW(snapshot, C.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return result


@dataclass(frozen=True)
class Snapshot:
    side: int
    characters: tuple[Character, ...]
    campaign: tuple[int, int, int]


class LiveReader:
    def __init__(self, game: Path | None = None):
        self.k = kernel_api()
        self.handle = self.resource = None
        self.names: dict[int, str] = {}
        try:
            pids = game_processes(self.k)
            if len(pids) != 1:
                raise PlannerError("Start Rebellion and load a campaign." if not pids
                                   else "More than one Rebellion process is running. Close the extra copy.")
            self.pid = pids[0]
            self.handle = self.k.OpenProcess(READ_ACCESS, False, self.pid)
            if not self.handle:
                raise PlannerError("Cannot read Rebellion. Run the game and planner as the same Windows user.")
            buffer = C.create_unicode_buffer(32768)
            length = W.DWORD(len(buffer))
            if not self.k.QueryFullProcessImageNameW(self.handle, 0, buffer, C.byref(length)):
                raise PlannerError("Cannot identify the running game executable")
            executable = Path(buffer.value).resolve(strict=True)
            self.game = executable.parent
            if game is not None and game.resolve(strict=True) != self.game:
                raise PlannerError("The selected installation is not the running game")
            if hashlib.sha256(executable.read_bytes()).hexdigest() != SUPPORTED_EXE:
                raise PlannerError("Unsupported REBEXE.EXE. Live offsets are validated for one original build; see the documentation.")
            if self.read(0x4EDC00, 5) != bytes.fromhex("0f bf 41 7e c3"):
                raise PlannerError("The loaded executable does not match the supported memory layout")
            self.resource = self.k.LoadLibraryExW(str(self.game / "TEXTSTRA.DLL"), None, 2)
            if not self.resource:
                raise PlannerError("Cannot read TEXTSTRA.DLL name resources")
            self.user = C.WinDLL("user32", use_last_error=True)
            self.user.LoadStringW.argtypes = [W.HMODULE, W.UINT, W.LPWSTR, C.c_int]
            self.user.LoadStringW.restype = C.c_int
            self.catalog = {}
            for table in ("MJCHARSD", "MNCHARSD"):
                for record in decode((self.game / "GData" / f"{table}.DAT").read_bytes(), table):
                    if record["Id"] in self.catalog:
                        raise PlannerError("Duplicate character ID across tables")
                    record["Name"] = self.name(record["TextStraDllId"])
                    self.catalog[record["Id"]] = record
        except Exception:
            self.close()
            raise

    def close(self):
        if self.resource:
            self.k.FreeLibrary(self.resource)
            self.resource = None
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def read(self, address: int, length: int) -> bytes:
        if not self.handle or not 0x10000 <= address < 0x80000000 or not 1 <= length <= 2 * 1024 * 1024:
            raise PlannerError("Game data is unavailable; load a campaign and reconnect")
        buffer = C.create_string_buffer(length)
        received = C.c_size_t()
        if (not self.k.ReadProcessMemory(self.handle, address, buffer, length, C.byref(received))
                or received.value != length):
            raise PlannerError("The game changed or closed during a read. Refresh the roster.")
        return buffer.raw

    def uint(self, address: int) -> int:
        return u32(self.read(address, 4))

    def name(self, resource: int) -> str:
        if resource not in self.names:
            buffer = C.create_unicode_buffer(1024)
            if not self.user.LoadStringW(self.resource, resource, buffer, len(buffer)):
                raise PlannerError(f"Missing name resource {resource}")
            self.names[resource] = buffer.value
        return self.names[resource]

    def session(self) -> tuple[int, int, int]:
        code = W.DWORD()
        if not self.k.GetExitCodeProcess(self.handle, C.byref(code)) or code.value != 259:
            raise PlannerError("Rebellion has closed. Start it and reconnect.")
        session = self.uint(0x6B14E4)
        player = self.uint(session + 0x0C)
        side = self.uint(player + 0x24)
        root = self.uint(0x6B2BB0)
        if side not in (1, 2) or not root:
            raise PlannerError("Load a campaign before connecting")
        return session, root, side

    def chunks(self):
        """Bounded scans of readable private pages only; skip guards and images."""
        address, total = 0, 0
        while address < 0x80000000:
            info = MemoryInfo()
            if not self.k.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
                break
            end = (info.base or 0) + info.size
            if end <= address:
                raise PlannerError("Unexpected memory region layout")
            if (info.state == 0x1000 and info.type == 0x20000
                    and info.protect & 0xFF in (4, 8, 0x40, 0x80) and not info.protect & 0x100):
                for start in range(info.base, min(end, 0x80000000), 1024 * 1024):
                    size = min(1024 * 1024 + CHARACTER_SIZE, end - start)
                    total += size
                    if total > 512 * 1024 * 1024:
                        raise PlannerError("Memory scan exceeded its supported size limit")
                    try:
                        yield start, self.read(start, size)
                    except PlannerError:
                        # Regions can disappear while the process is running.
                        continue
            address = end

    def location(self, pointer: int) -> tuple[str, int]:
        if not pointer:
            return "Unknown", 0
        try:
            data = self.read(pointer, 0x40)
            ident, class_ptr = u32(data, 0x18), u32(data, 0x2C)
            # FUN_004f62d0 uses an instance name when present, else the class name.
            if u32(data, 0x34):
                text_ptr = self.uint(u32(data, 0x34) + 4)
                name = bytearray()
                for i in range(256):
                    byte = self.read(text_ptr + i, 1)
                    if byte == b"\0":
                        if name:
                            return name.decode("cp1252"), pointer
                        break
                    name.extend(byte)
            # Fleets have generated names; don't mislabel them with a class name.
            vtable = u32(data)
            getter = self.uint(vtable + 4)
            code = self.read(getter, 6)
            family = u32(code, 1) if code[0] == 0xB8 and code[-1] == 0xC3 else 0
            if 8 <= family < 16:
                return f"Fleet #{ident}", pointer
            if class_ptr:
                return self.name(self.uint(class_ptr + 0x30) & 0xFFFF), pointer
        except PlannerError:
            pass
        return "Location unavailable", pointer

    def snapshot(self) -> Snapshot:
        session = self.session()
        side = session[2]
        pattern = re.compile(b"|".join(re.escape(struct.pack("<I", v)) for v in VTABLES))
        candidates: set[int] = set()
        for start, data in self.chunks():
            for match in pattern.finditer(data):
                address = start + match.start()
                if address % 4 == 0:
                    candidates.add(address)
        result = {}
        for address in sorted(candidates):
            try:
                data = self.read(address, CHARACTER_SIZE)
                character = decode_character(data, self.catalog, side)
                if character is None:
                    continue
                # Reciprocal view link excludes abandoned heap objects and stale copies.
                views = u32(data, 0x20)
                if self.uint(views + 0x24 + side * 4) != address:
                    continue
                class_ptr = u32(data, 0x2C)
                if (self.uint(class_ptr + 0x18) != character.id
                        or self.uint(class_ptr + 0x2C) != character.family):
                    continue
                location, location_id = self.location(u32(data, 0x1C))
                if self.read(address, CHARACTER_SIZE) != data:
                    raise PlannerError("Character changed while reading; refresh for a consistent snapshot")
                character = decode_character(data, self.catalog, side, location, location_id)
                if character.id in result:
                    raise PlannerError("Ambiguous live character objects; reconnect after loading finishes")
                result[character.id] = character
            except PlannerError as error:
                # Invalid/freed candidates are normal; ambiguity and torn live reads are not.
                if str(error).startswith(("Ambiguous", "Character changed")):
                    raise
        if self.session() != session:
            raise PlannerError("Campaign changed during refresh; reconnect")
        if not result:
            raise PlannerError("No recruited player characters found. Finish loading a campaign and reconnect.")
        return Snapshot(side, tuple(sorted(result.values(), key=lambda c: c.name)), session)
