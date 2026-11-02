"""Read the original game's open Create Mission dialog, without issuing orders."""
from __future__ import annotations

from dataclasses import dataclass
import struct
from collections.abc import Callable

from mission_data import PlannerError
from mission_live import LiveReader, u32

DIALOG_VTABLE = 0x65A218
ORDER_VTABLES = (0x65D118, 0x65D170)
SYSTEM_VTABLES = {0x663698: 0x90, 0x664098: 0x92}
MISSION_KEYS = {1: "Recruitment", 2: "Jedi training", 3: "Subdue uprising",
                4: "Ship research", 5: "Troop research", 6: "Facility research",
                7: "Diplomacy", 8: "Incite uprising", 9: "Espionage",
                10: "Reconnaissance", 11: "Assassination", 12: "Abduction",
                13: "Rescue", 14: "Death Star sabotage", 15: "Sabotage"}


def tree_nodes(read_uint, tree: int, limit: int = 4096) -> tuple[int, ...]:
    """Native intrusive tree: list +4 root, node +4 left, node +0x10 successor."""
    node = read_uint(tree + 4)
    seen = set()
    while node:
        if node in seen or len(seen) >= limit:
            raise PlannerError("Invalid or changing mission list")
        seen.add(node)
        left = read_uint(node + 4)
        if not left:
            break
        node = left
    seen.clear()
    result = []
    while node:
        if node in seen or len(seen) >= limit:
            raise PlannerError("Invalid or changing mission list")
        seen.add(node)
        result.append(node)
        node = read_uint(node + 0x10)
    return tuple(result)


@dataclass(frozen=True)
class MissionSetup:
    address: int
    hwnd: int
    page: int
    mission: str
    target: int
    target_name: str
    members: tuple[tuple[int, str], ...]
    context: dict[str, int | None]
    agent_hwnd: int
    decoy_hwnd: int


class SetupReader:
    def __init__(self, live: LiveReader, window_check: Callable[[int], bool] = lambda hwnd: True):
        self.live = live
        self.window_check = window_check
        self.cached = 0

    def find(self) -> MissionSetup | None:
        live = self.live
        session = live.session()
        needle = struct.pack("<I", DIALOG_VTABLE)
        # Cached dialog first; only discover again after it closes or becomes invalid.
        if self.cached:
            try:
                result = self.decode(self.cached, session[2])
            except PlannerError:
                result = None
            if result:
                if live.session() != session:
                    raise PlannerError("Campaign changed while reading mission setup")
                return result
        self.cached = 0
        for start, data in live.chunks():
            offset = 0
            while (offset := data.find(needle, offset)) >= 0:
                address = start + offset
                offset += 4
                if address % 4:
                    continue
                try:
                    result = self.decode(address, session[2])
                except PlannerError:
                    continue
                if result:
                    if live.session() != session:
                        raise PlannerError("Campaign changed while reading mission setup")
                    self.cached = address
                    return result
        return None

    def decode(self, address: int, side: int) -> MissionSetup | None:
        live = self.live
        data = live.read(address, 0x140)
        if u32(data) != DIALOG_VTABLE:
            return None
        hwnd, order, box = u32(data, 0x18), u32(data, 0x120), u32(data, 0x128)
        if not hwnd or not order or not box or not self.window_check(hwnd):
            return None
        order_data = live.read(order, 0x60)
        if u32(order_data) not in ORDER_VTABLES:
            return None
        view = u32(data, 0x114)
        if live.uint(view + 0x9C) != side:
            return None
        item = live.uint(box + 0xE0)
        key = live.uint(item + 0x0C)
        if key not in MISSION_KEYS:
            return None
        members = self.members(order)
        if not members or len(set(k for k, _ in members)) != len(members):
            return None
        target = u32(order_data, 0x34)
        name, context = self.target_context(target, side)
        check = live.read(address, 0x140)
        if (live.read(order, 0x60) != order_data or live.uint(box + 0xE0) != item
                or self.members(order) != members or check[:4] != data[:4]
                or check[0x18:0x1C] != data[0x18:0x1C] or check[0x114:] != data[0x114:]):
            raise PlannerError("Mission selection changed while reading")
        return MissionSetup(address, hwnd, u32(data, 0x118), MISSION_KEYS[key], target,
                            name, members, context,
                            live.uint(u32(data, 0x130) + 0x18),
                            live.uint(u32(data, 0x138) + 0x18))

    def members(self, order: int) -> tuple[tuple[int, str], ...]:
        live, members = self.live, []
        for offset, role in ((0x2C, "Agent"), (0x58, "Decoy")):
            for node in tree_nodes(live.uint, order + offset, 128):
                ident = live.uint(node + 0x18)
                if not 0x30 <= ident >> 24 < 0x40:
                    raise PlannerError("Unsupported mission member ID")
                members.append((ident, role))
        return tuple(members)

    def target_context(self, target: int, side: int) -> tuple[str, dict[str, int | None]]:
        live = self.live
        context = {"support": None, "stormtroopers": None, "target_combat": None}
        if not 0x90 <= target >> 24 < 0x98:
            return "Selected target", context
        for start, data in live.chunks():
            for vtable in SYSTEM_VTABLES:
                if SYSTEM_VTABLES[vtable] != target >> 24:
                    continue
                needle, offset = struct.pack("<I", vtable), 0
                while (offset := data.find(needle, offset)) >= 0:
                    address = start + offset
                    offset += 4
                    if address % 4:
                        continue
                    try:
                        obj = live.read(address, 0x90)
                        flags = u32(obj, 0x24)
                        if (u32(obj, 0x18) != target & 0xFFFFFF or flags >> 4 & 3 != side
                                or flags & 0x100 or live.uint(u32(obj, 0x20) + 0x24 + 4 * side) != address):
                            continue
                        record = u32(obj, 0x2C)
                        if (live.uint(record + 0x18) != target & 0xFFFFFF
                                or live.uint(record + 0x2C) != target >> 24):
                            continue
                        name = live.location(address)[0]
                        # Fully known own systems only. Never substitute master/enemy data.
                        if flags >> 6 & 3 != side:
                            return name, context
                        support = struct.unpack_from("<i", obj, 0x58)[0]
                        if not 0 <= support <= 100:
                            raise PlannerError("Invalid system support")
                        count = 0
                        for child in tree_nodes(live.uint, u32(obj, 0x28)):
                            unit = live.read(child, 0x54)
                            unit_flags = u32(unit, 0x24)
                            if (unit_flags >> 4 & 3 != side or unit_flags >> 6 & 3 != 2
                                    or unit_flags & 0x100 or not u32(unit, 0x50) & 1):
                                continue
                            record = u32(unit, 0x2C)
                            if record and live.uint(record + 0x2C) == 0x10 and live.uint(record + 0x18) == 6:
                                count += 1
                        if live.read(address, 0x90) != obj:
                            raise PlannerError("System changed while reading")
                        return name, {"support": support if side == 1 else 100 - support,
                                      "stormtroopers": count, "target_combat": None}
                    except PlannerError:
                        continue
        return "Selected target", context
