"""Synthetic binary fixtures only: no game assets are needed for these tests."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import rebellion as r


def fixture(table, entity=1001):
    schema = r.SCHEMAS[table]
    data = bytearray(16 + schema["record_size"])
    struct.pack_into("<4I", data, 0, 1, 1, 20, 28)
    values = {"Id": entity, "Field2_1": 1, "Field7_2": 2, "MaintenanceCost": 30}
    for field in schema["fields"]:
        struct.pack_into("<I" if field["type"] == "uint" else "<H", data,
                         16 + field["offset"], values.get(field["name"], 0))
    return bytes(data)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        (self.game / "GData").mkdir(parents=True)
        self.backup = self.root / "backup"
        self.preset_path = self.root / "preset.json"
        self.originals = {}
        self.preset = {"format_version": 1, "id": "synthetic-test", "tables": {}}
        for table in ("CAPSHPSD", "FIGHTSD"):
            name = f"{table}.DAT"
            original = fixture(table)
            self.originals[name] = original
            (self.game / "GData" / name).write_bytes(original)
            self.preset["tables"][name] = {"sha256": r.digest(original), "changes": [
                {"id": 1001, "field": "MaintenanceCost", "before": 30, "after": 24}]}
        self.save_preset()

    def save_preset(self):
        self.preset_path.write_text(json.dumps(self.preset), encoding="utf-8")

    def assert_originals(self):
        for name, original in self.originals.items():
            self.assertEqual((self.game / "GData" / name).read_bytes(), original)

    def test_plan_is_read_only_and_preserves_unedited_bytes(self):
        _, entries = r.plan(self.game, self.preset_path)
        self.assert_originals()
        self.assertFalse(self.backup.exists())
        for entry in entries:
            table = entry["name"][:-4]
            field = next(f for f in r.SCHEMAS[table]["fields"] if f["name"] == "MaintenanceCost")
            offset = 16 + field["offset"]
            self.assertEqual(entry["after"][:offset], entry["before"][:offset])
            self.assertEqual(entry["after"][offset + 4:], entry["before"][offset + 4:])
            self.assertEqual(r.decode(entry["after"], table)[0]["MaintenanceCost"], 24)

    def test_apply_restore_round_trip_and_repeated_restore(self):
        r.apply(self.game, self.preset_path, self.backup)
        for name, original in self.originals.items():
            self.assertEqual((self.backup / name).read_bytes(), original)
            self.assertNotEqual((self.game / "GData" / name).read_bytes(), original)
        r.restore(self.game, self.backup)
        r.restore(self.game, self.backup)
        self.assert_originals()
        self.assertTrue((self.backup / "manifest.json").exists())

    def test_validates_all_files_before_writing(self):
        path = self.game / "GData" / "FIGHTSD.DAT"
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaises(r.PatchError):
            r.apply(self.game, self.preset_path, self.backup)
        self.assertEqual((self.game / "GData" / "CAPSHPSD.DAT").read_bytes(), self.originals["CAPSHPSD.DAT"])
        self.assertFalse(self.backup.exists())

    def test_reapplication_refused(self):
        r.apply(self.game, self.preset_path, self.backup)
        with self.assertRaises(r.PatchError):
            r.apply(self.game, self.preset_path, self.root / "another-backup")
        self.assertFalse((self.root / "another-backup").exists())

    def test_existing_backup_never_overwritten(self):
        self.backup.mkdir()
        sentinel = self.backup / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            r.apply(self.game, self.preset_path, self.backup)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assert_originals()

    def test_backup_inside_game_refused(self):
        with self.assertRaises(r.PatchError):
            r.apply(self.game, self.preset_path, self.game / "backup")
        self.assert_originals()

    def test_restore_refuses_later_edits_before_any_write(self):
        r.apply(self.game, self.preset_path, self.backup)
        first = self.game / "GData" / "CAPSHPSD.DAT"
        first_patched = first.read_bytes()
        second = self.game / "GData" / "FIGHTSD.DAT"
        second.write_bytes(second.read_bytes() + b"later edit")
        with self.assertRaises(r.PatchError):
            r.restore(self.game, self.backup)
        self.assertEqual(first.read_bytes(), first_patched)
        self.assertTrue(second.read_bytes().endswith(b"later edit"))

    def test_corrupt_backup_refused(self):
        r.apply(self.game, self.preset_path, self.backup)
        (self.backup / "FIGHTSD.DAT").write_bytes(b"bad backup")
        with self.assertRaises(r.PatchError):
            r.restore(self.game, self.backup)
        self.assertEqual(r.decode((self.game / "GData" / "CAPSHPSD.DAT").read_bytes(), "CAPSHPSD")[0]["MaintenanceCost"], 24)

    def test_failed_second_write_rolls_back_first(self):
        real_write = r.atomic_write
        calls = 0

        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk failure")
            real_write(path, data)

        with patch.object(r, "atomic_write", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated disk failure"):
                r.apply(self.game, self.preset_path, self.backup)
        self.assert_originals()
        self.assertTrue((self.backup / "manifest.json").exists())

    def test_mixed_original_and_patched_state_can_be_restored(self):
        r.apply(self.game, self.preset_path, self.backup)
        (self.game / "GData" / "CAPSHPSD.DAT").write_bytes(self.originals["CAPSHPSD.DAT"])
        r.restore(self.game, self.backup)
        self.assert_originals()

    def test_changed_after_planning_refused(self):
        _, entries = r.plan(self.game, self.preset_path)
        entries[1]["path"].write_bytes(b"external change")
        with self.assertRaises(r.PatchError):
            r.commit_files(entries)
        self.assertEqual(entries[0]["path"].read_bytes(), entries[0]["before"])

    def test_invalid_values_duplicate_edits_and_structural_fields(self):
        original = copy.deepcopy(self.preset)
        for update in ({"after": -1}, {"after": 2 ** 32}, {"after": True},
                       {"before": 29}, {"after": 30}, {"field": "Id"}, {"id": 9999}):
            with self.subTest(update=update):
                self.preset = copy.deepcopy(original)
                self.preset["tables"]["CAPSHPSD.DAT"]["changes"][0].update(update)
                self.save_preset()
                with self.assertRaises(r.PatchError):
                    r.plan(self.game, self.preset_path)
                self.assert_originals()
        self.preset = copy.deepcopy(original)
        changes = self.preset["tables"]["CAPSHPSD.DAT"]["changes"]
        changes.append(copy.deepcopy(changes[0]))
        self.save_preset()
        with self.assertRaises(r.PatchError):
            r.plan(self.game, self.preset_path)

    def test_preset_and_backup_path_traversal_refused(self):
        self.preset["tables"]["../outside.DAT"] = self.preset["tables"].pop("FIGHTSD.DAT")
        self.save_preset()
        with self.assertRaises(r.PatchError):
            r.apply(self.game, self.preset_path, self.backup)
        self.assert_originals()
        self.backup.mkdir()
        (self.backup / "manifest.json").write_text(json.dumps({"format_version": 1, "files": {"../outside.DAT": {}}}))
        with self.assertRaises(r.PatchError):
            r.restore(self.game, self.backup)

    def test_decoder_rejects_truncation_bad_counts_and_duplicate_ids(self):
        original = fixture("CAPSHPSD")
        for bad in (original[:10], original[:-1], original + b"x", b"\0" * len(original)):
            with self.subTest(length=len(bad)):
                with self.assertRaises(r.PatchError):
                    r.decode(bad, "CAPSHPSD")
        duplicate = bytearray(original + original[16:])
        struct.pack_into("<I", duplicate, 4, 2)
        with self.assertRaisesRegex(r.PatchError, "duplicate"):
            r.decode(bytes(duplicate), "CAPSHPSD")

    def test_all_schema_offsets_are_contiguous(self):
        for name, schema in r.SCHEMAS.items():
            offset = 0
            for field in schema["fields"]:
                self.assertEqual(field["offset"], offset, name)
                offset += 4 if field["type"] == "uint" else 2
            self.assertEqual(offset, schema["record_size"], name)
            self.assertEqual(len(r.decode(fixture(name), name)), 1)

    def test_shipped_preset_has_valid_unique_edits(self):
        preset = r.load_json(r.DEFAULT_PRESET)
        changes = [(name, c["id"], c["field"]) for name, spec in preset["tables"].items() for c in spec["changes"]]
        self.assertTrue(changes)
        self.assertEqual(len(set(changes)), len(changes))
        self.assertTrue(all(r.valid_hash(s["sha256"]) for s in preset["tables"].values()))
        for filename, spec in preset["tables"].items():
            fields = {field["name"] for field in r.SCHEMAS[filename[:-4]]["fields"]}
            for change in spec["changes"]:
                self.assertIn(change["field"], fields & r.EDITABLE)
                self.assertNotEqual(change["before"], change["after"])
                self.assertTrue(change["reason"])


if __name__ == "__main__":
    unittest.main()
