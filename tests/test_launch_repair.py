import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launch_repair as repair


class LaunchRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.game = self.root / 'steamapps/common/鬼谷八荒'
        self.game.mkdir(parents=True)
        self.exe = self.game / 'guigubahuang.exe'
        self.exe.write_bytes(b'game binary must stay identical')
        self.old_mod = self.game / 'Mods/friend.dll'
        self.old_mod.parent.mkdir()
        self.old_mod.write_bytes(b'friend mod')
        self.manifest = self.root / 'steamapps/appmanifest_1468810.acf'
        self.before = ('"AppState"\r\n{\r\n "appid" "1468810"\r\n'
                       ' "installdir" "鬼谷八荒"\r\n "buildid" "unchanged"\r\n}\r\n').encode('utf-8')
        self.manifest.write_bytes(self.before)
        self.data = self.root / 'appdata'
        self.data.mkdir()
        self.patch('launch_repair.data_dir', return_value=self.data)
        self.save = self.patch('launch_repair.save_preferences')
        self.patch('launch_repair.unsupported_path', side_effect=lambda p: not str(p).isascii())
        self.short_path = self.patch('launch_repair.short_game_path', return_value=None)
        self.steam = self.patch('launch_repair.steam_running', return_value=False)
        self.processes = self.patch('game_setup.game_processes', return_value=set())
        if os.name != 'nt':
            self.patch('launch_repair.make_junction', side_effect=lambda t, s: s.symlink_to(t, target_is_directory=True))
        self.progress = []

    def patch(self, *args, **kwargs):
        patcher = patch(*args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def run_repair(self, stop=lambda: False):
        return repair.repair_game_path(self.game, lambda p, m: self.progress.append((p, m)), stop)

    def test_repair_updates_only_install_dir_preserves_binary_and_old_mod_path(self):
        result = self.run_repair()
        self.assertEqual(result.name, 'TaleOfImmortal')
        self.assertEqual(self.manifest.read_bytes(), self.before.replace('鬼谷八荒'.encode(), b'TaleOfImmortal'))
        self.assertEqual((result / self.exe.name).read_bytes(), b'game binary must stay identical')
        self.assertEqual(self.old_mod.read_bytes(), b'friend mod')
        self.assertTrue(repair.is_junction(self.game))
        self.assertEqual(self.game.resolve(), result.resolve())
        self.save.assert_called_once_with(game=str(result))
        self.assertEqual(next((self.data / 'launch-repairs').rglob('*.acf')).read_bytes(), self.before)
        self.assertFalse((self.data / 'launch-repair-pending.json').exists())
        self.assertEqual(self.run_repair(), result)

    def test_waits_for_steam_and_can_cancel_without_changes(self):
        self.steam.return_value = True
        self.patch('launch_repair.time.sleep')
        with self.assertRaises(InterruptedError):
            self.run_repair(stop=lambda: bool(self.progress))
        self.assertIn('Steam > Exit', self.progress[0][1])
        self.assertEqual(self.manifest.read_bytes(), self.before)
        self.assertFalse(repair.is_junction(self.game))
        self.assertFalse((self.game.parent / 'TaleOfImmortal').exists())

    def test_manifest_alias_to_chinese_folder_is_repaired_and_preserved(self):
        alias = self.game.with_name('TaleOfImmortal')
        repair.make_junction(self.game, alias)
        before = self.before.replace('鬼谷八荒'.encode(), b'TaleOfImmortal')
        self.manifest.write_bytes(before)
        result = self.run_repair()
        self.assertEqual(result.name, 'TaleOfImmortal-2')
        self.assertEqual(alias.resolve(), result.resolve())
        self.assertEqual(self.game.resolve(), result.resolve())
        self.assertEqual(self.manifest.read_bytes(), before.replace(b'"TaleOfImmortal"', b'"TaleOfImmortal-2"'))
        self.assertEqual(self.exe.read_bytes(), b'game binary must stay identical')

    def test_short_path_repairs_manifest_with_app_inside_game_and_reuses_it(self):
        alias = self.game.with_name('SHORT~1')
        repair.make_junction(self.game, alias)
        self.short_path.return_value = alias
        self.patch('launch_repair.data_dir', return_value=self.game / 'translator')
        result = self.run_repair()
        self.assertEqual(result, alias)
        self.assertFalse(repair.is_junction(self.game))
        self.assertEqual(alias.resolve(), self.game)
        self.assertEqual(self.manifest.read_bytes(), self.before.replace('鬼谷八荒'.encode(), b'SHORT~1'))
        self.steam.return_value = True
        self.assertEqual(self.run_repair(), alias)

    def test_short_path_preference_failure_recovers_from_committed_manifest(self):
        alias = self.game.with_name('SHORT~1')
        repair.make_junction(self.game, alias)
        self.short_path.return_value = alias
        self.save.side_effect = OSError('disk full')
        with self.assertRaises(OSError):
            self.run_repair()
        self.assertTrue((self.data / 'launch-repair-pending.json').exists())
        self.save.side_effect = None
        self.assertEqual(self.run_repair(), alias)

    def test_waits_for_game_to_be_saved_and_closed(self):
        self.processes.return_value = {123}
        self.patch('launch_repair.time.sleep')
        with self.assertRaises(InterruptedError):
            self.run_repair(stop=lambda: bool(self.progress))
        self.assertIn('Save and close', self.progress[0][1])
        self.assertEqual(self.exe.read_bytes(), b'game binary must stay identical')

    def test_destination_collision_never_merges_or_overwrites(self):
        occupied = self.game.with_name('TaleOfImmortal')
        occupied.mkdir()
        (occupied / 'keep').write_bytes(b'other game')
        result = self.run_repair()
        self.assertEqual(result.name, 'TaleOfImmortal-2')
        self.assertEqual((occupied / 'keep').read_bytes(), b'other game')

    def test_unrelated_manifest_rejected(self):
        for before in (self.before.replace(b'1468810', b'999'),
                       self.before.replace('鬼谷八荒'.encode(), b'other'),
                       self.before + b'"installdir" "duplicate"'):
            self.manifest.write_bytes(before)
            with self.assertRaisesRegex(ValueError, 'record does not match'):
                self.run_repair()
            self.assertEqual(self.manifest.read_bytes(), before)
            self.assertFalse(repair.is_junction(self.game))

    def test_bom_and_unrelated_manifest_fields_preserved(self):
        self.manifest.write_bytes(b'\xef\xbb\xbf' + self.before)
        self.run_repair()
        self.assertEqual(self.manifest.read_bytes(), b'\xef\xbb\xbf' + self.before.replace('鬼谷八荒'.encode(), b'TaleOfImmortal'))

    def test_junction_failure_rolls_directory_back(self):
        self.patch('launch_repair.make_junction', side_effect=PermissionError('blocked'))
        with self.assertRaisesRegex(PermissionError, 'blocked'):
            self.run_repair()
        self.assertFalse(repair.is_junction(self.game))
        self.assertTrue(self.exe.is_file())
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_manifest_write_failure_rolls_directory_back(self):
        write = repair.atomic_bytes
        def fail(path, payload):
            if path == self.manifest:
                raise PermissionError('manifest locked')
            write(path, payload)
        self.patch('launch_repair.atomic_bytes', side_effect=fail)
        with self.assertRaisesRegex(PermissionError, 'manifest locked'):
            self.run_repair()
        self.assertFalse(repair.is_junction(self.game))
        self.assertTrue(self.exe.is_file())
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_steam_reopening_rolls_directory_back(self):
        self.steam.side_effect = [False, False, True]
        with self.assertRaisesRegex(ValueError, 'Steam reopened'):
            self.run_repair()
        self.assertFalse(repair.is_junction(self.game))
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_interrupted_after_rename_recovers_on_retry(self):
        original = repair.make_junction
        with patch('launch_repair.make_junction', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_repair()
        self.assertFalse(self.game.exists())
        self.assertTrue((self.data / 'launch-repair-pending.json').is_file())
        from app_config import installed_game
        with patch('app_config.data_dir', return_value=self.data):
            self.assertEqual(installed_game(), self.game.with_name('TaleOfImmortal'))
        with patch('launch_repair.make_junction', side_effect=original):
            result = self.run_repair()
        self.assertEqual(result.name, 'TaleOfImmortal')
        self.assertTrue(self.exe.is_file())

    def test_preference_failure_recovers_from_committed_files(self):
        self.save.side_effect = OSError('preference disk full')
        with self.assertRaises(OSError):
            self.run_repair()
        self.assertTrue(repair.is_junction(self.game))
        self.save.side_effect = None
        self.assertEqual(self.run_repair().name, 'TaleOfImmortal')
        self.assertFalse((self.data / 'launch-repair-pending.json').exists())

    def test_manifest_changed_on_interruption_is_not_overwritten(self):
        with patch('launch_repair.make_junction', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_repair()
        newer = self.before.replace(b'unchanged', b'new Steam update')
        self.manifest.write_bytes(newer)
        with self.assertRaisesRegex(ValueError, 'record changed'):
            self.run_repair()
        self.assertEqual(self.manifest.read_bytes(), newer)

    def test_app_data_inside_installation_requires_extraction_elsewhere(self):
        self.patch('launch_repair.data_dir', return_value=self.game)
        with self.assertRaisesRegex(ValueError, 'Downloads'):
            self.run_repair()
        self.assertFalse(repair.is_junction(self.game))


if __name__ == '__main__':
    unittest.main()
