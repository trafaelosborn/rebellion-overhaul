"""Synthetic fixtures only: no game data, names, or memory dumps."""
from dataclasses import replace
import struct
import unittest

from mission_data import (Character, MISSION_BY_NAME, PlannerError, ProbabilityTable,
                          evaluate, skill_score, team_warnings)
from mission_live import CHARACTER_SIZE, READ_ACCESS, decode_character


class ProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.table = ProbabilityTable(((-10, 3), (0, 10), (20, 45), (100, 97)))
        self.character = Character(42, "Synthetic Agent", 0x30, 73, 59, 82, 95)

    def test_step_lookup_and_clamping(self):
        for score, expected in [(-1000, 3), (-10, 3), (-1, 3), (0, 10),
                                (19, 10), (20, 45), (99, 45), (100, 97), (999, 97)]:
            with self.subTest(score=score):
                self.assertEqual(self.table.lookup(score)[1], expected)

    def test_decode_signed_thresholds(self):
        data = struct.pack("<III", 1, 4, 13) + b"IntTableEntry"
        data += b"".join(struct.pack("<IIii", i + 1, 1, x, p) for i, (x, p) in enumerate(self.table.rows))
        self.assertEqual(ProbabilityTable.decode(data), self.table)
        for corrupt in (b"", data[:-1], data + b"x", b"\x02" + data[1:], data[:12] + b"X" + data[13:]):
            with self.assertRaises(PlannerError):
                ProbabilityTable.decode(corrupt)

    def test_reject_bad_rows(self):
        for rows in ((), ((0, -1),), ((0, 101),), ((0, 1), (0, 2)), ((5, 1), (-5, 2))):
            with self.assertRaises(PlannerError):
                ProbabilityTable(rows)

    def test_each_mission_input(self):
        cases = [("Espionage", {}, 59), ("Sabotage", {}, 70), ("Rescue", {}, 82),
                 ("Death Star sabotage", {}, 70), ("Diplomacy", {"support": 65, "stormtroopers": 2}, 10),
                 ("Recruitment", {"support": 30}, 65),
                 ("Incite uprising", {"support": 80, "stormtroopers": 3}, 12),
                 ("Subdue uprising", {"support": 80, "stormtroopers": 3}, 18),
                 ("Abduction", {"target_combat": 101}, -19),
                 ("Assassination", {"target_combat": 22}, 60)]
        for name, context, score in cases:
            with self.subTest(name=name):
                mission = MISSION_BY_NAME[name]
                result = evaluate(self.character, mission, {mission.table: self.table}, context)
                self.assertEqual(result.score, score)
                self.assertEqual(result.percent, self.table.lookup(score)[1])

    def test_unknown_target_is_not_assumed_zero(self):
        mission = MISSION_BY_NAME["Abduction"]
        self.assertIsNone(evaluate(self.character, mission, {mission.table: self.table}, {}).percent)
        self.assertIsNotNone(evaluate(self.character, mission, {mission.table: self.table}, {"target_combat": 0}).percent)

    def test_missing_support_and_invalid_input(self):
        mission = MISSION_BY_NAME["Diplomacy"]
        tables = {mission.table: self.table}
        self.assertIsNone(evaluate(self.character, mission, tables, {"support": 50}).percent)
        for value in (-1, 101, "50", True):
            with self.assertRaises(PlannerError):
                evaluate(self.character, mission, tables, {"support": value, "stormtroopers": 0})

    def test_decoys_have_no_mission_success_roll(self):
        mission = MISSION_BY_NAME["Sabotage"]
        roll = evaluate(self.character, mission, {mission.table: self.table}, {}, "Decoy")
        self.assertEqual(roll.score, 59)
        self.assertIsNone(roll.percent)

    def test_research_and_minor_recruitment_not_fake_zero_odds(self):
        for mission in [MISSION_BY_NAME["Ship research"], MISSION_BY_NAME["Recruitment"]]:
            minor = replace(self.character, family=0x38, ship_design=80)
            self.assertIsNone(evaluate(minor, mission, {mission.table: self.table}, {"support": 0}).percent)

    def test_missing_table_has_no_fallback_formula(self):
        self.assertIsNone(evaluate(self.character, MISSION_BY_NAME["Espionage"], {}, {}).percent)

    def test_team_location_and_readiness(self):
        first = replace(self.character, location_id=100)
        second = replace(first, id=43, location_id=200, status="En route")
        self.assertEqual(len(team_warnings([first, second])), 2)
        self.assertFalse(team_warnings([first, replace(first, id=43)]))


class LiveDecodeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {42: {"FamilyId": 0x38, "Name": "Synthetic Agent"}}
        self.data = bytearray(CHARACTER_SIZE)
        for offset, value in ((0, 0x665BE0), (0x18, 42), (0x24, 0x800000A1), (0x50, 0x30047)):
            struct.pack_into("<I", self.data, offset, value)
        struct.pack_into("<8h", self.data, 0x7C, 40, 65, 2, 3, 4, 121, 150, 100)

    def test_effective_not_base_skills(self):
        struct.pack_into("<8h", self.data, 0x58, *([1] * 8))
        c = decode_character(bytes(self.data), self.catalog, 2)
        self.assertEqual((c.diplomacy, c.espionage, c.combat, c.leadership), (40, 65, 121, 150))
        self.assertEqual((c.ship_design, c.troop_training, c.facility_design), (2, 3, 4))

    def test_hide_enemies_other_views_and_unrecruited(self):
        for offset, value in ((0x24, 0x80000062), (0x24, 0x80000081),
                              (0x24, 0x800001A1), (0x50, 0), (0x50, 0x3004F), (0xAC, 1)):
            with self.subTest(offset=offset, value=value):
                data = bytearray(self.data)
                struct.pack_into("<I", data, offset, value)
                self.assertIsNone(decode_character(bytes(data), self.catalog, 2))

    def test_bad_identity_or_stats_rejected(self):
        for offset, value in ((0, 0xDEADBEEF), (0x18, 900), (0x7C, 0xFFFF)):
            data = bytearray(self.data)
            struct.pack_into("<I", data, offset, value)
            self.assertIsNone(decode_character(bytes(data), self.catalog, 2))
        self.assertIsNone(decode_character(bytes(self.data[:-1]), self.catalog, 2))
        self.assertIsNone(decode_character(bytes(self.data), self.catalog, 0))

    def test_status_and_sort_skill(self):
        struct.pack_into("<I", self.data, 0x78, 0x80)
        c = decode_character(bytes(self.data), self.catalog, 2)
        self.assertEqual(c.status, "On mission")
        self.assertEqual(skill_score(c, MISSION_BY_NAME["Sabotage"]), 93)

    def test_access_does_not_request_writes_or_injection(self):
        self.assertEqual(READ_ACCESS, 0x410)
        self.assertFalse(READ_ACCESS & (0x20 | 0x08 | 0x02))


if __name__ == "__main__":
    unittest.main()
