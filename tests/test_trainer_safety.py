import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import trainer  # noqa: E402


def write_sol(path, entries):
    root = b'jy2'
    data = bytearray(b'TCSO' + b'\x00' * 6)
    data.extend(struct.pack('>H', len(root)))
    data.extend(root)
    data.extend(b'\x00' * 4)
    for key, kind, value in entries:
        key_bytes = key.encode('ascii')
        data.extend(struct.pack('>H', len(key_bytes)))
        data.extend(key_bytes)
        if kind == 'N':
            data.extend(b'\x00' + struct.pack('>d', float(value)))
        elif kind == 'B':
            data.extend(b'\x01' + bytes([1 if value else 0]))
        elif kind == 'S':
            value_bytes = value.encode('utf-8')
            data.extend(b'\x02' + struct.pack('>H', len(value_bytes)) + value_bytes)
        else:
            raise ValueError(kind)
    Path(path).write_bytes(data)


class NumberValidationTests(unittest.TestCase):
    def test_rejects_non_finite_fractional_and_negative_values(self):
        for value in ('nan', 'inf', '-inf', '1.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trainer.parse_game_number('LV', value)
        with self.assertRaises(ValueError):
            trainer.parse_game_number('S_M', '-1')

    def test_allows_signed_reputation_and_normal_integers(self):
        self.assertEqual(trainer.parse_game_number('X_Y', '-10'), -10)
        self.assertEqual(trainer.parse_game_number('LV', '99'), 99)


class AtomicSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'gamezly.sol'
        write_sol(self.path, [('LV', 'N', 1), ('name_1', 'S', '林')])

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_round_trips_values_and_uses_unique_backups(self):
        sol = trainer.Sol(str(self.path))
        first = sol.backup()
        second = sol.backup()
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(second).is_file())

        sol.set_number('LV', '7')
        sol.set_string('name_1', '令狐')
        sol.save()
        check = trainer.Sol(str(self.path))
        self.assertEqual(check.entries['LV']['val'], 7)
        self.assertEqual(check.entries['name_1']['val'], '令狐')

    def test_failed_verification_keeps_original_file(self):
        original = self.path.read_bytes()
        sol = trainer.Sol(str(self.path))
        sol.raw[:] = b'broken'
        with self.assertRaises(ValueError):
            sol.save()
        self.assertEqual(self.path.read_bytes(), original)

    def test_number_only_edit_passes_semantic_verification(self):
        sol = trainer.Sol(str(self.path))
        sol.set_number('LV', '8')
        sol.save()
        self.assertEqual(trainer.Sol(str(self.path)).entries['LV']['val'], 8)

    def test_modifier_lock_rejects_a_second_writer(self):
        with mock.patch.object(trainer, 'ensure_game_closed'):
            with trainer.edit_guard(str(self.path)):
                with self.assertRaises(RuntimeError):
                    with trainer.edit_guard(str(self.path)):
                        pass

    def test_plain_text_full_name_is_synchronized(self):
        write_sol(self.path, [
            ('name_1', 'S', '林'), ('name_2', 'S', '平之'), ('name', 'S', '林平之')])
        sol = trainer.Sol(str(self.path))
        sol.set_named('name_1', '令狐')
        sol.set_named('name_2', '沖')
        sol.set_full_name('令狐', '沖')
        sol.save()
        check = trainer.Sol(str(self.path))
        self.assertEqual(check.entries['name_1']['val'], '令狐')
        self.assertEqual(check.entries['name_2']['val'], '沖')
        self.assertEqual(check.entries['name']['val'], '令狐沖')

    def test_overlong_string_is_rejected_before_mutation(self):
        sol = trainer.Sol(str(self.path))
        before = bytes(sol.raw)
        with self.assertRaises(ValueError):
            sol.set_string('name_1', '字' * 30_000)
        self.assertEqual(bytes(sol.raw), before)


class SaveMigrationTests(unittest.TestCase):
    def test_copies_latest_old_namespace_without_deleting_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_root = Path(tmp) / 'save'
            old_a = save_root / 'localhost' / 'old-a' / 'jy2.swf'
            old_b = save_root / 'localhost' / 'old-b' / 'jy2.swf'
            target = save_root / 'localhost' / 'current' / 'jy2.swf'
            old_a.mkdir(parents=True)
            old_b.mkdir(parents=True)
            write_sol(old_a / 'gamezly.sol', [('LV', 'N', 2)])
            write_sol(old_b / 'gamezly.sol', [('LV', 'N', 9)])
            os.utime(old_a / 'gamezly.sol', (1, 1))
            os.utime(old_b / 'gamezly.sol', (2, 2))

            with mock.patch.object(trainer, 'pkg_save', return_value=str(save_root)), \
                    mock.patch.object(trainer, 'jy2_ns_dir', return_value=str(target)), \
                    mock.patch.object(trainer, 'ensure_game_closed'):
                migrated = trainer.migrate_legacy_slots()

            copied = target / 'gamezly.sol'
            self.assertEqual(len(migrated), 1)
            self.assertTrue(copied.is_file())
            self.assertTrue((old_a / 'gamezly.sol').is_file())
            self.assertTrue((old_b / 'gamezly.sol').is_file())
            self.assertEqual(trainer.Sol(str(copied)).entries['LV']['val'], 9)


if __name__ == '__main__':
    unittest.main()
