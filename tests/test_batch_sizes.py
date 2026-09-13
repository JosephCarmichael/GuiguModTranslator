import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_parallel_translation import PROFILE, project_with_batches, translated
from translation import translate, BatchTooLarge, request_batch, protect, restore
from extractor import read_json, save_project, extract, validate_translation
import app_config


class BatchSizeTests(unittest.TestCase):
    def test_narration_inside_angle_brackets_remains_visible_to_translator(self):
        source = '<灵力>\n<color=#ff0000>灵力{0}</color><sprite name="sword">'
        masked, tokens = protect(source)
        self.assertEqual(masked.count('灵力'), 2)
        result = restore(masked.replace('灵力', 'Spirit'), tokens)
        self.assertEqual(result, source.replace('灵力', 'Spirit'))
        self.assertEqual(validate_translation(source, result), '')
        self.assertTrue(validate_translation(source, result.replace('</color>', '')))
        self.assertEqual(validate_translation('<你回过神来。>', '<You regain your senses.>'), '')
        self.assertTrue(validate_translation('<你回过神来。>', 'You regain your senses.'))

    def test_percentage_followed_by_english_is_not_a_printf_placeholder(self):
        source = '风暴纱幕\n获得30%闪避，但受到伤害提升100%'
        target = 'Storm Veil\nGain 30% dodge, but take 100% more damage'
        self.assertEqual(validate_translation(source, target), '')
        masked, tokens = protect(source)
        self.assertEqual(restore(masked, tokens), source)
        self.assertTrue(validate_translation('% d 灵力', '% s Spirit'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        stub = patch('translation.service_profile', return_value=PROFILE)
        stub.start()
        self.addCleanup(stub.stop)

    def test_selected_batch_sizes_reduce_call_count_without_losing_entries(self):
        for size in (12, 24, 48, 96):
            with self.subTest(size=size):
                project = project_with_batches(16)
                sizes = []
                def request(texts, *_):
                    sizes.append(len(texts))
                    return translated(texts)
                with patch('translation.request_batch', request):
                    result = translate(project, self.folder, concurrency=4, batch_size=size)
                self.assertEqual(sizes, [size] * (192 // size))
                self.assertEqual(result['translated'], 192)
                self.assertTrue(all(u['translation'] == u['source'].replace('灵力', 'Spirit ') for u in project['units']))

    def test_character_target_keeps_complete_entries(self):
        project = project_with_batches(1)
        for i,u in enumerate(project['units']):
            u['source'] = '灵力' + str(i) + 'a' * 2995
        sizes = []
        with patch('translation.request_batch', side_effect=lambda texts, *_: (sizes.append(sum(map(len,texts))), translated(texts))[1]):
            translate(project, self.folder, batch_size=96)
        self.assertTrue(all(size <= 6000 for size in sizes))
        self.assertTrue(all(len(u['translation']) > 2995 for u in project['units']))

    def test_truncated_batches_split_until_they_fit(self):
        project = project_with_batches(8)
        sizes = []
        def request(texts, *_):
            sizes.append(len(texts))
            if len(texts) > 12:
                raise BatchTooLarge('Truncated')
            return translated(texts)
        with patch('translation.request_batch', request):
            result = translate(project, self.folder, batch_size=48, concurrency=4)
        self.assertEqual(result['translated'], 96)
        self.assertIn(48, sizes)
        self.assertIn(24, sizes)
        self.assertEqual(sizes.count(12), 8)

    def test_single_oversized_entry_is_reported_while_other_text_continues(self):
        project = project_with_batches(2)
        def request(texts, *_):
            if any(s.startswith('灵力0 ') for s in texts):
                raise BatchTooLarge('Truncated')
            return translated(texts)
        with patch('translation.request_batch', request):
            result = translate(project, self.folder, batch_size=24, concurrency=4)
        self.assertEqual((result['translated'], result['failed']), (23, 1))
        self.assertIn('response limit', project['units'][0]['translation_error'])

    def test_real_response_length_signal_triggers_split(self):
        with patch('translation.urllib.request.urlopen', return_value=io.BytesIO(b'{"choices":[{"finish_reason":"length"}]}')):
            with self.assertRaises(BatchTooLarge):
                request_batch(['灵力'], PROFILE, 'en', lambda: False)

    def test_provider_and_batch_change_preserves_existing_translations_after_rescan(self):
        mod = self.folder/'mod'
        mod.mkdir()
        (mod/'text.json').write_text(json.dumps([{'name': f'灵力{i}'} for i in range(96)],ensure_ascii=False), encoding='utf-8')
        info = {'id': 'resume', 'name': 'Resume test', 'path': str(mod)}
        project = extract(info, self.folder/'saved')
        for u in project['units'][:37]:
            u.update(translation='Saved '+u['id'], status='machine', model='deepseek-flash')
        save_project(project, self.folder/'saved')
        original = {u['id']: copy.deepcopy(u) for u in project['units'] if u['translation']}
        rescanned = extract(info, self.folder/'saved')
        sources = []
        def request(texts, *_):
            sources.extend(texts)
            return translated(texts)
        with patch('translation.service_profile', return_value={**PROFILE, 'provider': 'OpenRouter', 'model': 'openrouter-model'}), patch('translation.request_batch', request):
            result = translate(rescanned, self.folder/'saved', batch_size=48)
        self.assertEqual(result['total'], 59)
        self.assertEqual(len(sources), 59)
        for unit in read_json(self.folder/'saved/project.json')['units']:
            if unit['id'] in original:
                self.assertEqual(unit['translation'], original[unit['id']]['translation'])
                self.assertEqual(unit['model'], 'deepseek-flash')

    def test_batch_preferences_preserve_concurrency_and_game(self):
        with patch('app_config.data_dir', return_value=self.folder):
            self.assertEqual(app_config.translation_batch_size(), 48)
            app_config.save_preferences(game='game', concurrency=16, batch_size=96)
            self.assertEqual(app_config.translation_batch_size(), 96)
            app_config.save_preferences(concurrency=4)
            self.assertEqual(app_config.preferences()['batch_size'], 96)
            self.assertEqual(app_config.preferences()['game'], 'game')

    def test_invalid_batch_sizes_fail_before_any_requests(self):
        for size in (0, True, '48', 1024):
            with self.subTest(size=size), self.assertRaises(ValueError):
                translate(project_with_batches(1), self.folder, batch_size=size)


if __name__ == '__main__':
    unittest.main()
