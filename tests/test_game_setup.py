import hashlib
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import game_setup as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.game = self.root / 'game'; self.game.mkdir()
        self.assets = self.root / 'assets'; self.assets.mkdir()
        self.data = self.root / 'appdata'; self.data.mkdir()
        self.patch('game_setup.data_dir', return_value=self.data)
        self.patch('game_setup.game_processes', return_value=set())
        self.patch('game_setup.validate_game', side_effect=lambda p: Path(p).resolve())
        self.patch('game_setup.runtime_payload', return_value=b'MZtranslator')
        self.patch('game_setup.preflight', side_effect=ValueError('not set up'))
        self.patch('windows_prerequisites.ensure_prerequisites')
        self.patch('launch_repair.data_dir', return_value=self.data)
        self.manifest = {'melonloader_version': '0.5.4', 'assets': {}}
        for name in ['MelonLoader.x64.zip', *setup.CACHES]:
            with zipfile.ZipFile(self.assets / name, 'w') as z:
                if name == 'MelonLoader.x64.zip':
                    z.writestr('version.dll', b'MZproxy')
                    z.writestr('MelonLoader/MelonLoader.dll', b'MZmelon')
                else:
                    z.writestr('tool.exe', b'MZtool')
            self.hash_asset(name)
        self.save_manifest()
        self.patch('game_setup.ASSETS', self.assets)

    def patch(self, *args, **kwargs):
        p = patch(*args, **kwargs); self.addCleanup(p.stop); return p.start()

    def hash_asset(self, name):
        self.manifest['assets'][name] = {'sha256': hashlib.sha256((self.assets / name).read_bytes()).hexdigest()}

    def save_manifest(self):
        (self.assets / 'manifest.json').write_text(json.dumps(self.manifest))

    def write(self, name, data):
        p = self.game / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        return p

    def test_verified_bundle_installs_missing_loader_tools_and_plugin(self):
        pending, generation = setup.setup_plan(self.game)
        self.assertTrue(generation)
        store = self.write('UserData/GuiguModTranslator/installed.json', b'keep translations')
        mod = self.write('Mods/FriendsOtherMod.dll', b'keep mod')
        values = []
        setup.install_files(self.game, pending, lambda p, m: values.append(p), lambda: False)
        self.assertEqual((self.game / 'version.dll').read_bytes(), b'MZproxy')
        self.assertEqual((self.game / 'Mods/GuiguModTranslation.dll').read_bytes(), b'MZtranslator')
        self.assertTrue((self.game / setup.GENERATOR / 'Cpp2IL/tool.exe').is_file())
        self.assertEqual(store.read_bytes(), b'keep translations')
        self.assertEqual(mod.read_bytes(), b'keep mod')
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 45)

    def test_destination_accepts_an_alias_for_the_game_root(self):
        import os
        alias = self.root / 'game-alias'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(self.game), str(alias))
        else:
            alias.symlink_to(self.game, target_is_directory=True)
        self.assertEqual(setup.destination(alias, 'Mods/test.dll'), self.game / 'Mods/test.dll')

    def test_corrupt_archive_rejected_before_game_changes(self):
        with (self.assets / 'Cpp2IL.zip').open('ab') as f: f.write(b'corruption')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            setup.setup_plan(self.game)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_traversal_and_duplicate_names_rejected(self):
        for name in ('../outside.dll', 'MelonLoader/../../outside.dll', 'C:/evil.dll', 'MelonLoader/a:stream'):
            with self.subTest(name=name):
                with zipfile.ZipFile(self.assets / 'MelonLoader.x64.zip', 'w') as z: z.writestr(name, b'bad')
                self.hash_asset('MelonLoader.x64.zip'); self.save_manifest()
                with self.assertRaises(ValueError): setup.setup_plan(self.game)
        self.assertFalse((self.root / 'outside.dll').exists())

    def test_unknown_proxy_and_incompatible_loader_preserved(self):
        proxy = self.write('version.dll', b'MZother launcher')
        with self.assertRaisesRegex(ValueError, 'Another launcher'): setup.setup_plan(self.game)
        self.write('MelonLoader/MelonLoader.dll', b'MZnew loader')
        with patch('game_setup.melon_version', return_value=(0, 7, 3)):
            with self.assertRaisesRegex(ValueError, 'different MelonLoader'): setup.setup_plan(self.game)
        self.assertEqual(proxy.read_bytes(), b'MZother launcher')

    def test_working_compatible_files_are_preserved(self):
        proxy = self.write('version.dll', b'custom compatible proxy')
        core = self.write('MelonLoader/MelonLoader.dll', b'custom compatible loader')
        with patch('game_setup.melon_version', return_value=(0, 5, 4)):
            pending, _ = setup.setup_plan(self.game)
        self.assertNotIn('version.dll', pending)
        self.assertNotIn('MelonLoader/MelonLoader.dll', pending)
        self.assertEqual(core.read_bytes(), b'custom compatible loader')
        self.assertEqual(proxy.read_bytes(), b'custom compatible proxy')

    def test_cancel_restores_old_plugin_and_removes_added_files(self):
        plugin = self.write('Mods/GuiguModTranslation.dll', b'old')
        calls = []
        pending = {'new.dll': b'new', 'Mods/GuiguModTranslation.dll': b'new plugin'}
        def progress(*_): calls.append(1)
        with self.assertRaises(InterruptedError):
            setup.install_files(self.game, pending, progress, lambda: len(calls) >= 2)
        self.assertEqual(plugin.read_bytes(), b'old')
        self.assertFalse((self.game / 'new.dll').exists())
        backups = list((self.game / 'UserData/GuiguModTranslator/backups').rglob('GuiguModTranslation.dll'))
        self.assertEqual(backups[0].read_bytes(), b'old')

    def test_write_failure_rolls_back(self):
        original = setup.atomic_bytes
        def write(path, payload):
            if path.name == 'fail.dll': raise OSError('disk full')
            original(path, payload)
        with patch('game_setup.atomic_bytes', side_effect=write):
            with self.assertRaisesRegex(OSError, 'disk full'):
                setup.install_files(self.game, {'first.dll': b'a', 'fail.dll': b'b'}, lambda *_: None, lambda: False)
        self.assertFalse((self.game / 'first.dll').exists())

    def test_game_started_during_write_stops_and_rolls_back(self):
        with patch('game_setup.game_processes', side_effect=[set(), {123}]):
            with self.assertRaisesRegex(ValueError, 'started during setup'):
                setup.install_files(self.game, {'first.dll': b'a', 'second.dll': b'b'}, lambda *_: None, lambda: False)
        self.assertFalse((self.game / 'first.dll').exists())

    def status(self, pid=123, version='1.2.3', errors=None):
        return self.write('UserData/GuiguModTranslator/runtime-status.json',
                          json.dumps({'process_id': pid, 'version': version, 'errors': errors or [],
                                      'hooks': ['UnityEngine.UI.Text', 'Destiny localisation']}).encode())

    def test_live_check_rejects_old_process_before_accepting_new_status(self):
        started = time.time() - 1
        self.status(pid=999)
        stages = []
        def progress(p, m):
            stages.append(p); self.status()
        with patch('game_setup.game_processes', return_value={123}), patch('game_setup.time.sleep'), \
             patch('game_setup.preflight', return_value=b'MZ'):
            value = setup.wait_for_runtime(self.game, started, progress, lambda: False, timeout=5)
        self.assertEqual(value['process_id'], 123)
        self.assertEqual(len(stages), 1)

    def test_live_check_rejects_stale_file_even_with_current_pid(self):
        import os
        status = self.status(); os.utime(status, (1, 1))
        updates = []
        def progress(*_): updates.append(1); self.status()
        with patch('game_setup.game_processes', return_value={123}), patch('game_setup.time.sleep'), \
             patch('game_setup.preflight', return_value=b'MZ'):
            setup.wait_for_runtime(self.game, time.time() - 1, progress, lambda: False, timeout=5)
        self.assertEqual(len(updates), 1)

    def test_runtime_errors_never_report_ready(self):
        self.status(errors=['hook failed'])
        with patch('game_setup.game_processes', return_value={123}):
            with self.assertRaisesRegex(ValueError, 'hook failed'):
                setup.wait_for_runtime(self.game, time.time()-1, lambda *_: None, lambda: False)

    def test_first_setup_waits_for_runtime_and_leaves_retry_marker_on_failure(self):
        with patch('game_setup.setup_plan', return_value=({'Mods/GuiguModTranslation.dll': b'MZplugin'}, True)), \
             patch('game_setup.launch_game') as launch, patch('game_setup.wait_for_runtime', side_effect=ValueError('first launch failed')):
            with self.assertRaisesRegex(ValueError, 'first launch failed'):
                setup.ensure_setup(self.game)
        launch.assert_called_once_with(self.game, first_setup=True)
        self.assertTrue((self.game / 'UserData/GuiguModTranslator/setup-pending.json').is_file())
        self.assertFalse((self.game / 'UserData/GuiguModTranslator/setup-complete.json').exists())
        self.assertEqual(json.loads((self.data / 'setup-last.json').read_text())['state'], 'error')

    def test_retry_existing_files_still_checks_unfinished_first_launch(self):
        marker = self.write('UserData/GuiguModTranslator/setup-pending.json', b'{"started":1}')
        with patch('game_setup.setup_plan', return_value=({}, False)), patch('game_setup.launch_game') as launch, \
             patch('game_setup.wait_for_runtime', return_value={'process_id':123}) as wait:
            result = setup.ensure_setup(self.game)
        self.assertEqual(result['state'], 'ready'); launch.assert_called_once(); wait.assert_called_once()
        self.assertFalse(marker.exists())
        self.assertTrue((self.game / 'UserData/GuiguModTranslator/setup-complete.json').is_file())

    def test_existing_ready_setup_does_not_launch_game(self):
        with patch('game_setup.setup_plan', return_value=({}, False)), patch('game_setup.preflight', return_value=b'MZ'), \
             patch('game_setup.launch_game') as launch:
            self.assertEqual(setup.ensure_setup(self.game)['state'], 'ready')
        launch.assert_not_called()

    def test_cancel_while_game_open_does_not_touch_files(self):
        self.write('Mods/GuiguModTranslation.dll', b'old')
        progress = []
        with patch('game_setup.setup_plan', return_value=({'Mods/GuiguModTranslation.dll':b'new'}, False)), \
             patch('game_setup.game_processes', return_value={123}):
            with self.assertRaises(InterruptedError):
                setup.ensure_setup(self.game, lambda p,m: progress.append(p), lambda: 5 in progress)
        self.assertEqual((self.game / 'Mods/GuiguModTranslation.dll').read_bytes(), b'old')

    def test_setup_lock_released_after_exception(self):
        with self.assertRaises(ValueError):
            with setup.setup_lock(self.game): raise ValueError('crash')
        with setup.setup_lock(self.game): pass


if __name__ == '__main__': unittest.main()
