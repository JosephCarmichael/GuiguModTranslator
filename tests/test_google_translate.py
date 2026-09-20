import copy
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import app_config
import google_translate as google
from extractor import TOKENS
from translation import translate, request_batch, TranslationError
from translation_cost import estimate_project


def response(text):
    return io.BytesIO(json.dumps([[[text, 'source', None, None]], None, 'zh-CN']).encode())


class GoogleTests(unittest.TestCase):
    def setUp(self):
        for mocked in (patch.object(google, '_next_start', 0), patch.object(google, 'REQUEST_SPACING', 0)):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_google_profile_does_not_read_any_credential(self):
        with patch('api_access.selected_key', side_effect=AssertionError('Credentials read')):
            profile = app_config.service_profile(mode='google')
        self.assertTrue(profile['keyless'])
        self.assertNotIn('api_key', profile)

    def test_new_public_install_defaults_to_google_but_respects_saved_choice(self):
        with patch('app_config.build_edition', return_value='public'), patch('app_config.preferences', return_value={}):
            self.assertEqual(app_config.translation_mode(), 'google')
        with patch('app_config.build_edition', return_value='public'), patch('app_config.preferences', return_value={'translation_mode': 'free'}):
            self.assertEqual(app_config.translation_mode(), 'free')

    def test_no_authorization_and_all_google_sentence_parts_are_used(self):
        payload = io.BytesIO(json.dumps([[['Restore ', None], ['spirit.', None]]]).encode())
        with patch('google_translate.urllib.request.urlopen', return_value=payload) as http:
            result = request_batch(['恢复灵力'], app_config.service_profile(mode='google'), 'en', lambda: False)
        request = http.call_args.args[0]
        self.assertEqual(urllib.parse.urlsplit(request.full_url).hostname, 'translate.googleapis.com')
        self.assertIsNone(request.get_header('Authorization'))
        self.assertNotIn('key=', request.full_url)
        self.assertEqual(result, ['Restore spirit.'])
        self.assertEqual(result.model, 'google-web')

    def test_tokens_newlines_numbers_and_glossary_are_preserved(self):
        source = '<color=red>恢复{0}灵力</color>\r\n获得50%宝剑123\\V[2]'
        seen = []
        def fetch(text, target, stop, gate):
            seen.append(text)
            return {'恢复': 'Restore', '获得': 'Gain'}[text]
        with patch('google_translate.fetch', side_effect=fetch):
            result = google.translate_text(source, 'en', lambda: False, {'灵力': 'spirit', '宝剑': 'sword'})
        self.assertEqual(TOKENS.findall(source), TOKENS.findall(result))
        self.assertIn('\r\n', result)
        self.assertIn('123', result)
        self.assertEqual(seen, ['恢复', '获得'])
        self.assertIn('spirit', result)
        self.assertIn('sword', result)

    def test_long_text_is_split_without_exceeding_request_size(self):
        with patch('google_translate.fetch', return_value='Sword') as fetch:
            google.translate_text('宝剑' * 1200, 'en', lambda: False)
        self.assertGreater(fetch.call_count, 1)
        self.assertTrue(all(len(call.args[0]) <= google.MAX_CHARS for call in fetch.call_args_list))

    def test_throttling_and_invalid_responses_do_not_retry_or_switch_provider(self):
        error = urllib.error.HTTPError(google.ENDPOINT, 429, 'busy', {}, io.BytesIO(b'{}'))
        with patch('google_translate.urllib.request.urlopen', side_effect=error) as http:
            with self.assertRaisesRegex(TranslationError, 'HTTP 429'):
                google.request_batch(['宝剑'], 'en', lambda: False)
        self.assertEqual(http.call_count, 1)
        for payload in ({'error': 'changed'}, [], [[]], [[['仍然中文', None]]]):
            with self.subTest(payload=payload), patch.object(google, '_next_start', 0), \
                 patch('google_translate.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaisesRegex(TranslationError, 'unsupported response'):
                    google.request_batch(['宝剑'], 'en', lambda: False)

    def test_cancel_during_pacing_never_sends_a_request(self):
        with patch.object(google, '_next_start', float('inf')), patch('google_translate.urllib.request.urlopen') as http:
            with self.assertRaises(InterruptedError):
                google.fetch('宝剑', 'en', lambda: True)
        http.assert_not_called()

    def test_failed_second_entry_preserves_first_and_resume_reuses_it(self):
        project = {'mod': {'id': 'google-test'}, 'coverage': {'files': [], 'counts': {}},
                   'units': [{'id': str(i), 'source': s, 'translation': '', 'category': 'player_text',
                              'status': 'untranslated', 'occurrences': []} for i, s in enumerate(['宝剑', '灵力'])]}
        profile = app_config.service_profile(mode='google')
        with tempfile.TemporaryDirectory() as folder, patch('translation.service_profile', return_value=profile):
            with patch('google_translate.fetch', side_effect=['Sword', TranslationError('Throttled')]):
                with self.assertRaisesRegex(TranslationError, 'Throttled'):
                    translate(project, folder, concurrency=128, batch_size=96)
            saved = json.loads((Path(folder) / 'project.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['units'][0]['translation'], 'Sword')
            self.assertEqual(saved['units'][0]['engine'], 'google-web')
            self.assertEqual(saved['units'][1]['translation'], '')
            with patch('google_translate.fetch', return_value='Spirit') as fetch:
                result = translate(saved, folder)
            self.assertEqual((result['translated'], result['concurrency']), (1, 1))
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(estimate_project(saved, mode='google')['pence'], '0')
