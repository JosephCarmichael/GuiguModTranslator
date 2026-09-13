import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer
from extractor import extract, save_project


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.mod = self.root / 'mod'
        self.mod.mkdir()
        self.source = self.mod / 'text.json'
        self.source.write_text('{"name":"宝剑","desc":"恢复{0}灵力","icon":"图标"}', encoding='utf-8')
        self.before = self.source.read_bytes()
        self.project = extract({'id': 'one', 'name': 'One', 'path': str(self.mod)}, self.root / 'project')
        for unit in self.project['units']:
            unit.update(translation={'宝剑': 'Sword', '恢复{0}灵力': 'Restore {0} spirit', '图标': 'icon'}[unit['source']], status='edited')
        stub = patch('installer.preflight', return_value=b'MZfixture-loader')
        stub.start()
        self.addCleanup(stub.stop)

    def test_install_updates_and_uninstall_keep_source_and_other_mod(self):
        result = installer.install(self.project, self.game)
        self.assertEqual(result['count'], 2)
        loader, store = installer.paths(self.game)
        self.assertEqual(loader.read_bytes(), b'MZfixture-loader')
        self.assertNotIn('图标', installer.read_store(store)['mods']['one']['entries'])
        second = copy.deepcopy(self.project)
        second['mod'].update(id='two', name='Two')
        installer.install(second, self.game)
        installer.uninstall('one', self.game)
        self.assertEqual(set(installer.read_store(store)['mods']), {'two'})
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(len(list((store.parent / 'backups').glob('*.json'))), 2)

    def test_conflict_installs_with_new_priority_and_preserves_other_dictionary(self):
        installer.install(self.project, self.game)
        loader, store = installer.paths(self.game)
        original = store.read_bytes()
        second = copy.deepcopy(self.project)
        second['mod'].update(id='two', name='Two')
        next(u for u in second['units'] if u['source'] == '宝剑')['translation'] = 'Treasure sword'
        result = installer.install(second, self.game)
        self.assertEqual(result['conflicts_resolved'], 1)
        mods = installer.read_store(store)['mods']
        self.assertEqual(mods['one']['entries']['宝剑'], 'Sword')
        self.assertEqual(mods['two']['entries']['宝剑'], 'Treasure sword')
        self.assertGreater(mods['two']['install_order'], mods['one']['install_order'])
        self.assertIn(original, [p.read_bytes() for p in (store.parent/'backups').glob('*.json')])
        self.assertEqual(self.source.read_bytes(), self.before)
        installer.uninstall('two', self.game)
        self.assertEqual(installer.read_store(store)['mods']['one'], mods['one'])
        self.assertFalse(store.with_suffix('.lock').exists())

    def test_duplicate_project_text_prefers_manual_edit_without_mutating_project(self):
        machine = copy.deepcopy(next(u for u in self.project['units'] if u['source'] == '宝剑'))
        machine.update(id='000', status='machine', translation='Treasure sword')
        self.project['units'].insert(0, machine)
        original = copy.deepcopy(self.project)
        result = installer.install(self.project, self.game)
        self.assertEqual(result['conflicts_resolved'], 1)
        _, store = installer.paths(self.game)
        self.assertEqual(installer.read_store(store)['mods']['one']['entries']['宝剑'], 'Sword')
        self.assertEqual(self.project, original)
        self.project['units'].reverse()
        installer.install(self.project, self.game)
        self.assertEqual(installer.read_store(store)['mods']['one']['entries']['宝剑'], 'Sword')

    def test_reinstall_takes_priority_and_identical_text_is_not_a_conflict(self):
        installer.install(self.project, self.game)
        second = copy.deepcopy(self.project)
        second['mod'].update(id='two', name='Two')
        self.assertEqual(installer.install(second, self.game)['conflicts_resolved'], 0)
        next(u for u in self.project['units'] if u['source'] == '宝剑')['translation'] = 'Edited sword'
        self.assertEqual(installer.install(self.project, self.game)['conflicts_resolved'], 1)
        _, store = installer.paths(self.game)
        mods = installer.read_store(store)['mods']
        self.assertGreater(mods['one']['install_order'], mods['two']['install_order'])
        self.assertEqual(mods['two']['entries']['宝剑'], 'Sword')

    def test_legacy_store_gets_install_priority_and_backup(self):
        installer.install(self.project, self.game)
        _, store = installer.paths(self.game)
        old = installer.read_store(store)
        old['mods']['one'].pop('install_order')
        store.write_text(json.dumps(old), encoding='utf-8')
        second = copy.deepcopy(self.project)
        second['mod']['id'] = 'two'
        installer.install(second, self.game)
        self.assertEqual(installer.read_store(store)['mods']['two']['install_order'], 1)

    def test_conflict_success_message_includes_resolution_and_review_counts(self):
        message = installer.installation_message({'count': 125, 'conflicts_resolved': 3}, partial=True)
        self.assertIn('Installed 125', message)
        self.assertIn('resolved 3 text conflicts', message)
        self.assertIn('still needs review', message)

    def test_invalid_and_review_entries_never_reach_runtime(self):
        for unit in self.project['units']:
            if unit['source'] == '恢复{0}灵力':
                unit['translation'] = 'Restore spirit'
        result = installer.install(self.project, self.game)
        self.assertEqual((result['count'], result['skipped']), (1, 1))
        for unit in self.project['units']:
            unit['status'] = 'needs_review'
        with self.assertRaisesRegex(ValueError, 'No validated'):
            installer.install(self.project, self.game)

    def test_failed_store_write_rolls_back_new_loader(self):
        with patch('installer.commit_store', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                installer.install(self.project, self.game)
        loader, store = installer.paths(self.game)
        self.assertFalse(loader.exists())
        self.assertFalse(store.exists())

    def test_existing_loader_restored_on_store_failure(self):
        installer.install(self.project, self.game)
        loader, store = installer.paths(self.game)
        loader.write_bytes(b'MZprevious')
        original = store.read_bytes()
        with patch('installer.commit_store', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): installer.install(self.project, self.game)
        self.assertEqual(loader.read_bytes(), b'MZprevious')
        self.assertEqual(store.read_bytes(), original)

    def test_lock_prevents_lost_updates(self):
        _, store = installer.paths(self.game)
        with installer.locked(store):
            with self.assertRaisesRegex(ValueError, 'Another installation'):
                installer.install(self.project, self.game)

    def test_corrupt_store_preserved(self):
        _, store = installer.paths(self.game)
        store.parent.mkdir(parents=True)
        store.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError): installer.install(self.project, self.game)
        self.assertEqual(store.read_text(encoding='utf-8'), '{broken')

    def test_workflow_installs_and_cancel_does_not(self):
        from mod_workflow import run_job
        with patch('mod_workflow.preflight'), patch('mod_workflow.extract', return_value=self.project), \
             patch('mod_workflow.translate', return_value={'cancelled': False}):
            result = run_job(self.project['mod'], self.root/'project', lambda _: None, lambda: False, self.game)
            self.assertEqual(result['installation']['state'], 'installed')
        installer.uninstall('one', self.game)
        with patch('mod_workflow.preflight'), patch('mod_workflow.extract', return_value=self.project):
            result = run_job(self.project['mod'], self.root/'project', lambda _: None, lambda: True, self.game)
            self.assertEqual(result['state'], 'cancelled')
        self.assertFalse(installer.installation_status(self.game)['mods'])


if __name__ == '__main__':
    unittest.main()
