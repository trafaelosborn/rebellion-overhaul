"""Synthetic native dialog, tree, and player-view fixtures; no game dumps."""
from dataclasses import replace
import struct
import unittest
from unittest.mock import Mock

from mission_data import Character, PlannerError, ProbabilityTable
from mission_inline import NativePanel, member_lines
from mission_setup import DIALOG_VTABLE, MissionSetup, SetupReader, tree_nodes


class Memory:
    base = 0x100000

    def __init__(self):
        self.data = bytearray(0x8000)

    def put(self, address, value):
        struct.pack_into("<I", self.data, address-self.base, value)

    def read(self, address, length):
        if not self.base <= address <= self.base + len(self.data)-length:
            raise PlannerError("Unmapped synthetic pointer")
        return bytes(self.data[address-self.base:address-self.base+length])

    def uint(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def chunks(self):
        yield self.base, bytes(self.data)

    def session(self):
        return self.base+0x7000, self.base+0x7100, 2

    def location(self, address):
        return "Synthetic System", address


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.mem = m = Memory()
        self.dialog = d = m.base
        self.order = o = m.base+0x1000
        box, item, view = m.base+0x2000, m.base+0x2100, m.base+0x2200
        self.agent = a = m.base+0x3000
        self.decoy = b = m.base+0x3100
        self.system = s = m.base+0x4000
        views, record, children = m.base+0x4200, m.base+0x4300, m.base+0x4400
        unit, unit_record = m.base+0x4500, m.base+0x4600
        for address, value in ((d, DIALOG_VTABLE), (d+0x18, 99), (d+0x114, view),
                               (view+0x9C, 2), (d+0x118, 152), (d+0x120, o), (d+0x128, box),
                               (box+0xE0, item), (item+0x0C, 7), (d+0x130, box+0x300),
                               (d+0x138, box+0x400), (box+0x318, 101), (box+0x418, 102),
                               (o, 0x65D118), (o+0x30, a), (a+0x18, 0x3000002A),
                               (o+0x5C, b), (b+0x18, 0x3800002B), (o+0x34, 0x90000009),
                               (s, 0x663698), (s+0x18, 9), (s+0x20, views), (s+0x24, 0xA0),
                               (s+0x2C, record), (record+0x18, 9), (record+0x2C, 0x90),
                               (views+0x2C, s), (s+0x58, 30), (s+0x28, children),
                               (children+4, unit), (unit+0x24, 0xA0), (unit+0x50, 1),
                               (unit+0x2C, unit_record), (unit_record+0x18, 6),
                               (unit_record+0x2C, 0x10)):
            m.put(address, value)
        self.reader = SetupReader(m, lambda hwnd: hwnd == 99)

    def test_follows_native_selection_and_own_system_context(self):
        setup = self.reader.find()
        self.assertEqual(setup.mission, "Diplomacy")
        self.assertEqual(setup.members, ((0x3000002A, "Agent"), (0x3800002B, "Decoy")))
        self.assertEqual(setup.context, {"support": 70, "stormtroopers": 1, "target_combat": None})
        self.mem.put(self.mem.base+0x210C, 1)
        self.assertEqual(self.reader.find().mission, "Recruitment")

    def test_role_move_changes_the_reading(self):
        self.mem.put(self.order+0x30, 0)
        self.mem.put(self.decoy+0x10, self.agent)
        self.assertEqual(self.reader.find().members, ((0x3800002B, "Decoy"), (0x3000002A, "Decoy")))

    def test_enemy_neutral_and_master_views_never_supply_target_inputs(self):
        for flags in (0x60, 0x20, 0x80):
            with self.subTest(flags=flags):
                self.mem.put(self.system+0x24, flags)
                context = self.reader.find().context
                self.assertTrue(all(value is None for value in context.values()))

    def test_non_system_target_does_not_invent_combat(self):
        self.mem.put(self.order+0x34, 0x38000300)
        self.assertTrue(all(v is None for v in self.reader.find().context.values()))

    def test_duplicate_and_cyclic_members_rejected(self):
        self.mem.put(self.decoy+0x18, 0x3000002A)
        self.assertIsNone(self.reader.find())
        self.mem.put(self.decoy+0x18, 0x3800002B)
        self.mem.put(self.agent+0x10, self.agent)
        with self.assertRaises(PlannerError):
            self.reader.decode(self.dialog, 2)

    def test_closed_cached_dialog_does_not_mask_new_window(self):
        self.assertEqual(self.reader.find().hwnd, 99)
        new = self.mem.base+0x5000
        self.mem.data[new-self.mem.base:new-self.mem.base+0x140] = self.mem.read(self.dialog, 0x140)
        self.mem.put(new+0x18, 100)
        self.reader.window_check = lambda hwnd: hwnd == 100
        self.assertEqual(self.reader.find().hwnd, 100)
        self.assertEqual(self.reader.cached, new)

    def test_campaign_change_on_cached_read_fails_closed(self):
        self.reader.find()
        sessions = iter([(1, 2, 2), (3, 4, 2)])
        self.mem.session = lambda: next(sessions)
        with self.assertRaisesRegex(PlannerError, "Campaign changed"):
            self.reader.find()

    def test_changing_member_list_rejected_even_with_same_root(self):
        original_read, reads = self.mem.read, 0

        def read(address, length):
            nonlocal reads
            if address == self.agent+0x18:
                reads += 1
                if reads == 2:
                    self.mem.put(address, 0x3000002C)
            return original_read(address, length)

        self.mem.read = read
        with self.assertRaisesRegex(PlannerError, "selection changed"):
            self.reader.decode(self.dialog, 2)

    def test_bad_system_identity_or_support_stays_unknown(self):
        for address, value in ((self.mem.base+0x432C, 0x92), (self.system+0x58, 101),
                               (self.mem.base+0x422C, 0)):
            old = self.mem.uint(address)
            self.mem.put(address, value)
            self.assertIsNone(self.reader.find().context["support"])
            self.mem.put(address, old)

    def test_tree_order_and_bounded_walk(self):
        m = self.mem
        m.put(self.agent+4, self.decoy)
        m.put(self.decoy+0x10, self.agent)
        self.assertEqual(tree_nodes(m.uint, self.order+0x2C), (self.decoy, self.agent))
        with self.assertRaises(PlannerError):
            tree_nodes(m.uint, self.order+0x2C, limit=1)
        m.put(self.decoy+4, self.agent)
        with self.assertRaises(PlannerError):
            tree_nodes(m.uint, self.order+0x2C)


class PanelMeaningTests(unittest.TestCase):
    def setUp(self):
        self.character = Character(42, "Synthetic Agent", 0x30, 60, 80, 120, 90)
        self.roster = {42: self.character}
        self.setup = MissionSetup(1, 2, 0, "Sabotage", 0, "Synthetic target",
                                  ((0x3000002A, "Agent"),), {}, 3, 4)
        self.tables = {"SBTGMSTB": ProbabilityTable(((0, 7), (100, 63)))}

    def test_combined_skill_and_conditional_label(self):
        _, skills, odds, detail = member_lines(self.setup, self.roster, self.tables, 0)
        self.assertIn("ESP 80", skills)
        self.assertIn("COM 120", skills)
        self.assertIn("63%", odds)
        self.assertIn("score 100", odds)
        self.assertIn("excludes interception", detail)

    def test_decoy_never_gets_success_percent(self):
        setup = replace(self.setup, members=((0x3000002A, "Decoy"),))
        lines = member_lines(setup, self.roster, self.tables, 0)
        self.assertEqual(lines[1], "ESP 80")
        self.assertIn("no mission-success roll", lines[2])
        self.assertNotIn("%", " ".join(lines))

    def test_unknown_target_is_explicit(self):
        setup = replace(self.setup, mission="Abduction")
        lines = member_lines(setup, self.roster, self.tables, 0)
        self.assertIn("unknown target", lines[2])
        self.assertNotIn("%", " ".join(lines))

    def test_unsupported_unit_and_missing_character_do_not_reuse_readings(self):
        for key in (0x3C00002A, 0x3000002B):
            setup = replace(self.setup, members=((key, "Agent"),))
            lines = member_lines(setup, self.roster, self.tables, 0)
            self.assertNotIn("Synthetic Agent", lines[0])
            self.assertEqual(lines[2], "Roll: unknown")

    def test_pager_cycles_roles_and_research_has_no_percent(self):
        setup = replace(self.setup, members=((0x3000002A, "Agent"), (0x3000002A, "Decoy")))
        self.assertIn("decoy", member_lines(setup, self.roster, self.tables, -1)[0])
        self.assertIn("agent", member_lines(setup, self.roster, self.tables, 2)[0])
        lines = member_lines(replace(self.setup, mission="Ship research"), self.roster, self.tables, 0)
        self.assertNotIn("%", " ".join(lines))


class PanelPointerTests(unittest.TestCase):
    def setUp(self):
        self.panel = p = NativePanel.__new__(NativePanel)
        p.panel, p.mouse_down, p.index = 123, False, 0
        p.user = u = Mock()
        u.GetAsyncKeyState.return_value = 0x8000
        u.IsWindowVisible.return_value = True
        u.GetForegroundWindow.return_value = 10
        u.GetAncestor.return_value = 10
        u.WindowFromPoint.return_value = 123

        def cursor(point):
            point._obj.x, point._obj.y = 192, 8  # right pager at width 236
            return True

        def rect(hwnd, value):
            value._obj.right = 236
            return True

        u.GetCursorPos.side_effect = cursor
        u.GetClientRect.side_effect = rect
        u.ScreenToClient.return_value = True

    def test_a_held_button_and_duplicate_delivery_cycle_only_once(self):
        self.panel.pointer()
        self.panel.pointer()
        self.assertEqual(self.panel.index, 1)
        self.panel.user.GetAsyncKeyState.return_value = 0
        self.panel.pointer()
        self.panel.user.GetAsyncKeyState.return_value = 0x8000
        self.panel.pointer()
        self.assertEqual(self.panel.index, 2)

    def test_inactive_game_hidden_panel_and_covering_popup_ignore_clicks(self):
        for function, value in (("GetForegroundWindow", 11), ("IsWindowVisible", False),
                                ("WindowFromPoint", 456)):
            self.setUp()
            getattr(self.panel.user, function).return_value = value
            self.panel.pointer()
            self.assertEqual(self.panel.index, 0)
            self.panel.user.PostQuitMessage.assert_not_called()

    def test_dragging_into_panel_does_not_click_it(self):
        self.panel.user.WindowFromPoint.return_value = 456
        self.panel.pointer()
        self.panel.user.WindowFromPoint.return_value = 123
        self.panel.pointer()
        self.assertEqual(self.panel.index, 0)


if __name__ == "__main__":
    unittest.main()
