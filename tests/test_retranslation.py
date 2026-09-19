import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from translation import translate, TranslationError
from saved_translations import status_of
from mod_titles import load_titles, save_titles, translate_titles

PROFILE = {'api_key': 'fixture', 'model': 'fixture-model', 'provider': 'OpenRouter'}


class RetranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {'mod': {'id': 'retranslation-fixture'}, 'coverage': {'files': []}, 'units': [
            {'id': 'one', 'source': '宝剑 {0}', 'translation': 'Bad wording {0}', 'status': 'edited',
             'category': 'player_text', 'occurrences': []}]}

    def test_retranslation_uses_settings_and_backs_up_old_text(self):
        with patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=lambda texts, *a, **kw: [t.replace('宝剑', 'Sword') for t in texts]) as request:
            result = translate(self.project, self.root, retranslate=True, concurrency=4, batch_size=12)
        self.assertEqual(result['translated'], 1)
        self.assertEqual(request.call_args.args[1], PROFILE)
        self.assertEqual(self.project['units'][0]['translation'], 'Sword {0}')
        backup = json.loads(next((self.root / 'retranslation-backups').glob('*.json')).read_text())
        self.assertEqual(backup['units'][0]['translation'], 'Bad wording {0}')
        self.assertTrue(status_of(self.project)['complete'])

    def test_failed_retranslation_preserves_old_text_but_cannot_claim_complete(self):
        with patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=TranslationError('HTTP 402')):
            with self.assertRaises(TranslationError):
                translate(self.project, self.root, retranslate=True)
        self.assertEqual(self.project['units'][0]['translation'], 'Bad wording {0}')
        self.assertFalse(status_of(self.project)['complete'])
        with patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=lambda texts, *a, **kw: [t.replace('宝剑', 'Sword') for t in texts]) as request:
            translate(self.project, self.root)
        request.assert_called_once()
        self.assertTrue(status_of(self.project)['complete'])

    def test_bad_new_output_does_not_destroy_previous_wording(self):
        with patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', return_value=['Sword']):
            translate(self.project, self.root, retranslate=True)
        self.assertEqual(self.project['units'][0]['translation'], 'Bad wording {0}')
        self.assertFalse(status_of(self.project)['complete'])

    def test_missing_placeholders_chinese_and_whitespace_cannot_tick(self):
        for value in ('Sword', '宝剑 {0}', '   '):
            self.project['units'][0]['translation'] = value
            self.assertFalse(status_of(self.project)['complete'])

    def test_title_can_be_retranslated_and_is_reused_on_next_launch(self):
        mod = {'id': '1', 'name': '宝剑门'}
        titles = {'1': {'source': mod['name'], 'title': 'Old Sect'}}
        with patch('mod_titles.data_dir', return_value=self.root), patch('app_config.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', return_value=['Sword Sect']) as request:
            translate_titles([mod], titles, retranslate=True)
            self.assertEqual(load_titles()['1']['title'], 'Sword Sect')
            translate_titles([mod], load_titles())
            self.assertEqual(request.call_count, 1)

    def test_invalid_saved_titles_are_retried(self):
        with patch('mod_titles.data_dir', return_value=self.root):
            save_titles({'1': {'source': '宝剑门', 'title': '宝剑门'}})
            self.assertEqual(load_titles(), {})


if __name__ == '__main__':
    unittest.main()
