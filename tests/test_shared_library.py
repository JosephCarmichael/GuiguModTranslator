import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shared_library as library
from extractor import atomic_json


class SharedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('RESOURCE_DIR', self.root), ('data_dir', lambda: self.root / 'data')]:
            patcher = patch.object(library, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.project = {'mod': {'id': '123', 'name': '宝剑门', 'path': 'private local path'},
                        'units': [{'id': 'one', 'source': '灵力 {0}', 'translation': 'Spirit {0}', 'status': 'edited',
                                   'category': 'player_text', 'occurrences': ['private path']}],
                        'coverage': {'files': []}}
        atomic_json(self.root / 'projects' / '123' / 'project.json', self.project)

    def export(self):
        return library.export_library(self.root / 'projects', self.root / 'shared-library',
                                      {'123': {'source': '宝剑门', 'title': 'Sword Sect'}})

    def test_export_contains_only_valid_text_and_no_local_metadata(self):
        result = self.export()
        self.assertEqual((result['mods'], result['entries'], result['titles']), (1, 1, 1))
        payload = next((self.root / 'shared-library').glob('*.gz')).read_bytes()
        raw = gzip.decompress(payload).decode()
        self.assertNotIn('private', raw)
        self.assertNotIn('occurrences', raw)
        self.assertEqual(library.decode(payload)['translations'], {'灵力 {0}': 'Spirit {0}'})

    def test_diagnostic_copies_cannot_overwrite_the_main_saved_project(self):
        copy_project = copy.deepcopy(self.project)
        copy_project['units'][0]['translation'] = 'Diagnostic wording {0}'
        atomic_json(self.root / 'projects' / 'z-diagnostic-copy' / 'project.json', copy_project)
        self.export()
        payload = next((self.root / 'shared-library').glob('*.gz')).read_bytes()
        self.assertEqual(library.decode(payload)['translations'], {'灵力 {0}': 'Spirit {0}'})

    def test_exact_matches_reuse_without_overwriting_local_edits(self):
        self.export()
        local = copy.deepcopy(self.project)
        self.assertEqual(library.apply_shared(local), 0)
        local['units'][0]['translation'] = ''
        self.assertEqual(library.apply_shared(local, 'fr'), 0)
        self.assertEqual(library.apply_shared(local), 1)
        self.assertEqual(local['units'][0]['status'], 'shared')
        local['units'][0].update(source='灵力 {1}', translation='')
        self.assertEqual(library.apply_shared(local), 0)

    def test_shared_text_never_replaces_requested_retranslation(self):
        self.export()
        local = copy.deepcopy(self.project)
        local['units'][0].update(translation='', retranslation_pending=True)
        self.assertEqual(library.apply_shared(local), 0)

    def test_damaged_cache_and_wrong_hash_are_ignored(self):
        self.export()
        path = next((self.root / 'shared-library').glob('*.gz'))
        path.write_bytes(b'corrupt')
        local = copy.deepcopy(self.project)
        local['units'][0]['translation'] = ''
        self.assertEqual(library.apply_shared(local), 0)

    def test_titles_match_the_current_name_and_keep_local_title(self):
        self.export()
        titles = {}
        self.assertEqual(library.reuse_titles([self.project['mod']], titles), 1)
        titles['123']['title'] = 'My Sword Sect'
        self.assertEqual(library.reuse_titles([self.project['mod']], titles), 0)
        self.assertEqual(titles['123']['title'], 'My Sword Sect')
        renamed = {**self.project['mod'], 'name': '新宝剑门'}
        self.assertEqual(library.reuse_titles([renamed], {}), 0)

    def test_shared_text_avoids_api_configuration_and_requests_entirely(self):
        self.export()
        local = copy.deepcopy(self.project)
        local['units'][0]['translation'] = ''
        from translation import translate
        with patch('translation.service_profile') as profile, patch('translation.request_batch') as request:
            result = translate(local, self.root / 'output')
        self.assertEqual(result['total'], 0)
        profile.assert_not_called()
        request.assert_not_called()
        self.assertEqual(local['units'][0]['translation'], 'Spirit {0}')

    def test_private_download_uses_verified_cache_on_second_run(self):
        self.export()
        payload = next((self.root / 'shared-library').glob('*.gz')).read_bytes()
        with patch('github_client.repository_file', return_value=payload) as download:
            self.assertTrue(library.sync_mod(self.project['mod']))
            self.assertTrue(library.sync_mod(self.project['mod']))
        self.assertEqual(download.call_count, 1)

    def test_bad_remote_checksum_keeps_previous_file(self):
        self.export()
        with patch('github_client.repository_file', return_value=b'bad'):
            with self.assertRaises(ValueError):
                library.sync_mod(self.project['mod'])
        self.assertFalse((library.cache_root() / (library.library_key(self.project['mod']) + '.json.gz')).exists())

    def test_local_namespace_is_stable_across_computers(self):
        self.assertEqual(library.library_key({'id': 'local-aaa', 'namespace': 'unique-mod'}),
                         library.library_key({'id': 'local-bbb', 'namespace': 'unique-mod'}))

    def test_a_newer_bundled_index_is_not_overridden_by_stale_downloads(self):
        self.export()
        old = {'schema': 1, 'mods': {}, 'titles': {}, 'updated_at': '2000-01-01T00:00:00+00:00'}
        atomic_json(library.cache_root() / 'index.json', old)
        self.assertIn(library.library_key(self.project['mod']), library.load_index()['mods'])


if __name__ == '__main__':
    unittest.main()
