import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from destinies import scan_destinies, destiny_report
from extractor import save_project, read_json
from installer import install_detector, paths


class DestinyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.game = Path(temp.name)
        self.mod = self.game / 'mod'
        self.mod.mkdir()
        self.info = {'id': 'fixture', 'path': str(self.mod), 'name': 'Fixture'}
        self.folder = self.game / 'project'

    def write(self, name, value):
        path = self.mod / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def scan(self):
        return scan_destinies(self.game, self.folder, mods=[self.info])

    def fixture(self):
        self.write('ModExportData.cache', {'items': {
            'RoleCreateFeature': [
                {'id': '-42', 'type': '1', 'name': 'born_name', 'tips': 'born_tips',
                 'introduceText': '天生剑客', 'weight': '0'},
                {'id': '43', 'type': '2', 'name': '不属于先天'},
                {'id': '44', 'type': '1', 'name': 'base_game_key', 'tips': '0'}],
            'LocalText': [{'id': 1, 'key': 'born_name', 'ch': '剑痴', 'en': 'Sword Fanatic'},
                          {'id': 2, 'key': 'born_tips', 'ch': '<r>剑法{0}</r>', 'en': ''}]}})

    def test_all_three_fields_negative_ids_zero_weight_and_unresolved_keys(self):
        self.fixture()
        project = self.scan()
        self.assertEqual({u['source'] for u in project['units']}, {'剑痴', '<r>剑法{0}</r>', '天生剑客'})
        report = destiny_report(project)
        self.assertEqual(report['missing_texts'], 2)
        self.assertEqual({f['field'] for f in report['missing_fields']}, {'tips', 'introduceText'})
        self.assertEqual(report['unresolved_fields'][0]['key'], 'base_game_key')
        self.assertTrue((self.folder / 'untranslated-destinies.json').exists())

    def test_invalid_or_partly_chinese_installed_text_is_missing_and_edits_survive(self):
        self.fixture()
        _, store = paths(self.game)
        store.parent.mkdir(parents=True)
        store.write_text(json.dumps({'format': 'guigu-installed-v1', 'mods': {
            'a': {'source_path': str(self.mod), 'install_order': 1, 'entries': {'天生剑客': 'Born swordsman'}},
            'b': {'source_path': str(self.mod), 'install_order': 2,
                  'entries': {'天生剑客': 'Born 剑客', '<r>剑法{0}</r>': 'Sword {0}'}}}}), encoding='utf-8')
        project = self.scan()
        self.assertEqual(destiny_report(project)['missing_texts'], 2)
        unit = next(u for u in project['units'] if u['source'] == '天生剑客')
        unit.update(translation='Natural swordsman', status='edited')
        save_project(project, self.folder)
        self.assertEqual(read_json(self.folder / 'untranslated-destinies.json')['missing_texts'], 1)
        rescanned = self.scan()
        self.assertEqual(next(u['translation'] for u in rescanned['units'] if u['source'] == unit['source']), 'Natural swordsman')

    def test_loose_tables_and_runtime_inventory_include_unhovered_and_dynamic_text(self):
        self.write('ModExcel/RoleCreateFeature.json', [{'id': 1, 'type': 1, 'name': 'key'}])
        runtime_file = self.game / 'UserData/GuiguModTranslator/destiny-inventory.json'
        runtime_file.parent.mkdir(parents=True)
        runtime_file.write_text(json.dumps({'format': 'guigu-destinies-v1', 'process_id': 123,
            'destiny_count': 2, 'fields': [
                {'destiny_id': '1', 'field': 'name', 'key': 'key', 'source': '剑痴', 'unresolved': False},
                {'destiny_id': '2', 'field': 'tips', 'key': 'other', 'source': '灵力上限增加', 'unresolved': False}],
            'observed_untranslated': ['<color=red>灵力增加10</color>']}), encoding='utf-8')
        report = destiny_report(self.scan())
        self.assertEqual(report['missing_texts'], 3)
        self.assertEqual(report['unresolved_fields'], [])
        self.assertEqual(report['runtime_inventory']['destiny_count'], 2)

    def test_cancel_keeps_saved_project(self):
        self.fixture()
        self.scan()
        before = (self.folder / 'project.json').read_bytes()
        with self.assertRaises(InterruptedError):
            scan_destinies(self.game, self.folder, stop=lambda: True, mods=[self.info])
        self.assertEqual(before, (self.folder / 'project.json').read_bytes())

    def test_failed_new_process_does_not_silently_reuse_old_inventory(self):
        self.fixture()
        folder = self.game / 'UserData/GuiguModTranslator'
        folder.mkdir(parents=True)
        (folder / 'destiny-inventory.json').write_text(json.dumps({
            'format': 'guigu-destinies-v1', 'process_id': 1, 'fields': [
                {'destiny_id': '999', 'field': 'tips', 'source': '陈旧文本', 'unresolved': False}]}), encoding='utf-8')
        (folder / 'runtime-status.json').write_text(json.dumps({
            'process_id': 2, 'errors': ['Destiny inventory: void TValue_REF..ctor(intptr)']}), encoding='utf-8')
        project = self.scan()
        self.assertNotIn('陈旧文本', [u['source'] for u in project['units']])
        report = destiny_report(project)
        self.assertIsNone(report['runtime_inventory'])
        self.assertEqual(len(report['runtime_warnings']), 2)

    def test_detector_install_preserves_dictionaries_and_backs_up_loader(self):
        loader, store = paths(self.game)
        loader.parent.mkdir(parents=True)
        store.parent.mkdir(parents=True)
        loader.write_bytes(b'old loader')
        store.write_bytes(b'existing dictionary bytes')
        with patch('installer.preflight', return_value=b'MZnew loader'):
            self.assertTrue(install_detector(self.game))
            self.assertFalse(install_detector(self.game))
        self.assertEqual(store.read_bytes(), b'existing dictionary bytes')
        self.assertEqual(loader.read_bytes(), b'MZnew loader')
        self.assertEqual(next((store.parent / 'backups').glob('*.dll')).read_bytes(), b'old loader')


if __name__ == '__main__':
    unittest.main()
