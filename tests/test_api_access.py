import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import api_access
import app_config
from translation import translate, TranslationError
from translation_cost import enforce_translation_policy

SHARED = 'sk-or-v1-' + 'shared-test-' * 6
PERSONAL = 'sk-or-v1-' + 'personal-test-' * 6


def expensive():
    return {'mod': {'id': 'full-mod'}, 'coverage': {'files': [], 'counts': {}},
            'units': [{'id': 'one', 'source': '宝剑' * 50000, 'translation': '',
                       'category': 'player_text', 'status': 'untranslated', 'occurrences': []}]}


@unittest.skipUnless(os.name == 'nt', 'Windows personal-key storage uses real DPAPI')
class ApiAccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root/'data'; self.data.mkdir()
        self.resources = self.root/'resources'; self.resources.mkdir()
        (self.resources/'bundled_service.json').write_text(json.dumps({'api_key': SHARED}))
        for module in ('api_access', 'app_config'):
            self.patch(module+'.data_dir', return_value=self.data)
            self.patch(module+'.RESOURCE_DIR', self.resources)
        self.patch('translation_cost.is_friends_build', return_value=True)

    def patch(self, *args, **kwargs):
        p = patch(*args, **kwargs); self.addCleanup(p.stop); return p.start()

    def test_shared_default_stays_limited_and_never_requests(self):
        profile = app_config.service_profile()
        self.assertFalse(profile['personal_key'])
        self.assertEqual(profile['api_key'], SHARED)
        with patch('translation.request_batch') as request:
            with self.assertRaises(PermissionError):
                translate(expensive(), self.root/'output')
        request.assert_not_called()

    def test_save_encrypts_key_and_reloads_it_for_openrouter(self):
        api_access.save_openrouter_key('  ' + PERSONAL + '  ')
        raw = (self.data/api_access.ACCESS_FILE).read_text()
        self.assertNotIn(PERSONAL, raw)
        self.assertNotIn('sk-or-', raw)
        profile = app_config.service_profile()
        self.assertTrue(profile['personal_key'])
        self.assertEqual(profile['api_key'], PERSONAL)
        self.assertEqual(profile['endpoint'], 'https://openrouter.ai/api/v1/chat/completions')
        self.assertTrue(api_access.using_personal_key())

    def test_personal_key_unlocks_full_mod_and_is_used_by_requests(self):
        api_access.save_openrouter_key(PERSONAL)
        with patch('translation.request_batch', return_value=['Sword']) as request:
            result = translate(expensive(), self.root/'output')
        self.assertEqual(result['translated'], 1)
        self.assertEqual(request.call_args.args[1]['api_key'], PERSONAL)
        self.assertTrue(request.call_args.args[1]['personal_key'])
        saved = (self.root/'output/project.json').read_text(encoding='utf-8')
        self.assertNotIn(PERSONAL, saved)

    def test_policy_and_requests_share_one_credential_snapshot(self):
        api_access.save_openrouter_key(PERSONAL)
        original = enforce_translation_policy
        def switch_after_policy(*args, **kwargs):
            original(*args, **kwargs)
            api_access.use_shared_key()
        with patch('translation_cost.enforce_translation_policy', side_effect=switch_after_policy), \
             patch('translation.request_batch', return_value=['Sword']) as request:
            self.assertEqual(translate(expensive(), self.root/'output')['translated'], 1)
        self.assertEqual(request.call_args.args[1]['api_key'], PERSONAL)
        self.assertEqual(app_config.service_profile()['api_key'], SHARED)

    def test_remove_restores_shared_even_with_legacy_local_service(self):
        legacy = self.data/'service.json'
        legacy.write_text(json.dumps({'api_key': PERSONAL}))
        api_access.save_openrouter_key(PERSONAL)
        api_access.use_shared_key()
        self.assertEqual(json.loads((self.data/api_access.ACCESS_FILE).read_text()), {'mode': 'shared'})
        self.assertEqual(app_config.service_profile()['api_key'], SHARED)
        self.assertFalse(api_access.using_personal_key())
        with self.assertRaises(PermissionError):
            enforce_translation_policy(expensive())
        self.assertTrue(legacy.is_file())

    def test_invalid_input_keeps_saved_key(self):
        api_access.save_openrouter_key(PERSONAL)
        before = (self.data/api_access.ACCESS_FILE).read_bytes()
        for value in ('', 'Bearer '+PERSONAL, 'sk-deepseek-12345', 'sk-or-short', PERSONAL+'\nextra'):
            with self.subTest(value=value[:10]):
                with self.assertRaises(ValueError):
                    api_access.save_openrouter_key(value)
                self.assertEqual((self.data/api_access.ACCESS_FILE).read_bytes(), before)

    def test_shared_key_cannot_be_relabelled_to_remove_limit(self):
        with self.assertRaisesRegex(ValueError, 'shared key keeps'):
            api_access.save_openrouter_key(SHARED)
        (self.data/'service.json').write_text(json.dumps({'api_key': SHARED, 'personal_key': True}))
        self.assertFalse(app_config.service_profile()['personal_key'])
        with self.assertRaises(PermissionError):
            enforce_translation_policy(expensive())

    def test_corrupt_or_unreadable_key_never_falls_back_to_shared(self):
        for value in ('{broken', '{"mode":"personal","protected_key":"invalid"}',
                      '{"mode":"unexpected"}'):
            (self.data/api_access.ACCESS_FILE).write_text(value)
            with patch('translation.request_batch') as request:
                with self.assertRaisesRegex(ValueError, 'saved OpenRouter key'):
                    translate(expensive(), self.root/'output')
            request.assert_not_called()
        api_access.save_openrouter_key(PERSONAL)
        with patch('api_access._crypt', side_effect=ValueError('wrong Windows account')):
            with self.assertRaisesRegex(ValueError, 'saved OpenRouter key'):
                app_config.service_profile()

    def test_failed_key_save_preserves_existing_setting(self):
        api_access.use_shared_key()
        before = (self.data/api_access.ACCESS_FILE).read_bytes()
        with patch('api_access._crypt', side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError):
                api_access.save_openrouter_key(PERSONAL)
        self.assertEqual((self.data/api_access.ACCESS_FILE).read_bytes(), before)

    def test_personal_key_request_failure_never_switches_to_shared(self):
        api_access.save_openrouter_key(PERSONAL)
        with patch('translation.request_batch', side_effect=TranslationError('OpenRouter HTTP 401')) as request:
            with self.assertRaisesRegex(TranslationError, 'HTTP 401'):
                translate(expensive(), self.root/'output')
        self.assertTrue(request.call_args_list)
        self.assertTrue(all(call.args[1]['api_key'] == PERSONAL for call in request.call_args_list))
        self.assertTrue(api_access.using_personal_key())


if __name__ == '__main__':
    unittest.main()
