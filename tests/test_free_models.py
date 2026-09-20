import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import app_config
import free_models
from translation import request_batch, translate, TranslationError
from translation_cost import estimate_project, format_pence, enforce_translation_policy
from test_parallel_translation import project_with_batches, translated

PROFILE = {'provider': 'OpenRouter', 'model': 'free-pool', 'api_key': 'fixture-free-key',
           'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
           'free_only': True, 'minimum_intelligence': 30}


def model(ident='lab/strong:free', score=35):
    return {'id': ident, 'name': ident, 'pricing': {'prompt': '0', 'completion': '0'},
            'context_length': 32768, 'top_provider': {'max_completion_tokens': 8192},
            'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']},
            'benchmarks': {'artificial_analysis': {'intelligence_index': score}}}


def response(values, ident='lab/strong:free'):
    return io.BytesIO(json.dumps({'model': ident, 'usage': {'cost': 0},
        'choices': [{'message': {'content': json.dumps(values)}}]}).encode())


class SelectionTests(unittest.TestCase):
    def test_only_scored_free_text_models_with_sufficient_limits_qualify(self):
        rows = [model(), model('lab/boundary:free', 30), model('lab/weak:free', 29.9),
                model('lab/unscored:free', None), model('lab/paid', 80), model('openrouter/auto:free', 90)]
        for changes in ({'pricing': {'prompt': '0', 'completion': '0.1'}},
                        {'pricing': {'prompt': '0', 'completion': '0', 'request': '.01'}},
                        {'pricing': {'prompt': '0'}}, {'context_length': 8000},
                        {'top_provider': {'max_completion_tokens': 4096}},
                        {'architecture': {'input_modalities': ['text'], 'output_modalities': ['audio']}}):
            rows.append({**model('lab/excluded:free', 99), **changes})
        self.assertEqual([m['id'] for m in free_models.select_models(rows, 30)],
                         ['lab/strong:free', 'lab/boundary:free'])
        self.assertEqual(free_models.select_models([model(score=None)], 0), [])

    def test_invalid_thresholds_and_nonfinite_scores_are_rejected(self):
        for value in (True, -1, 101, float('nan'), float('inf'), 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                free_models.select_models([], value)
        for value in (True, 'NaN', 'Infinity'):
            self.assertEqual(free_models.select_models([model(score=value)], 0), [])

    def test_catalog_cached_and_expired_catalog_never_used_on_failure(self):
        with patch.object(free_models, '_catalog', None), patch.object(free_models, '_checked', 0), \
             patch('free_models.time.monotonic', return_value=1000), \
             patch('free_models.urllib.request.urlopen', return_value=io.BytesIO(json.dumps({'data': [model()]}).encode())) as http:
            self.assertEqual(free_models.discover(30), free_models.discover(30))
            self.assertEqual(http.call_count, 1)
            with patch('free_models.time.monotonic', return_value=2000), \
                 patch('free_models.urllib.request.urlopen', side_effect=OSError('offline')):
                with self.assertRaisesRegex(ValueError, 'Could not verify'):
                    free_models.discover(30)

    def test_empty_pool_fails_without_substituting_router(self):
        with patch.object(free_models, '_catalog', [model(score=20)]), \
             patch.object(free_models, '_checked', free_models.time.monotonic()):
            with self.assertRaisesRegex(ValueError, 'No verified free'):
                free_models.discover(30)

    def test_pacing_rotation_and_cancellation_share_the_key(self):
        with patch.object(free_models, '_accounts', {}):
            account = free_models.account(PROFILE)
            self.assertIs(account, free_models.account({**PROFILE, 'minimum_intelligence': 40}))
            models = ['first', 'second']
            self.assertEqual(account.order(models), models)
            self.assertEqual(account.order(models), models[::-1])
            with patch('free_models.time.monotonic', return_value=10):
                account.acquire(lambda: False)
                self.assertEqual(account.next_start, 13.1)
                account.defer(20)
                self.assertEqual(account.next_start, 30)
                with self.assertRaises(InterruptedError):
                    account.acquire(lambda: True)


class FreeRequestTests(unittest.TestCase):
    def setUp(self):
        self.models = free_models.select_models([model(), model('lab/second:free', 32)], 30)
        for mocked in (patch('free_models.discover', return_value=self.models),
                       patch('free_models.FreeAccount.acquire'), patch('free_models.FreeAccount.defer'),
                       patch.object(free_models, '_accounts', {}),
                       patch('translation_balance.tracker'), patch('translation.retry_delay', return_value=0)):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_zero_price_cap_on_every_attempt_and_retry_uses_next_model(self):
        calls = []
        def http(request, timeout):
            body = json.loads(request.data)
            calls.append(body)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, 'busy', {'Retry-After': '0'}, io.BytesIO(b'{}'))
            return response(['Spirit'], body['model'])
        with patch('translation.urllib.request.urlopen', http):
            values = request_batch(['灵力'], PROFILE, 'en', lambda: False)
        self.assertEqual([c['model'] for c in calls], ['lab/strong:free', 'lab/second:free'])
        self.assertEqual(values.model, 'lab/second:free')
        for call in calls:
            self.assertEqual(call['provider']['max_price'], {'prompt': 0, 'completion': 0, 'request': 0})
            self.assertNotIn('models', call)

    def test_invalid_json_and_changed_placeholders_try_other_models(self):
        for first in (io.BytesIO(b'{"choices": []}'), response(['Spirit']), response(['灵力\\V[900000]'])):
            with self.subTest(first=first), patch('translation.urllib.request.urlopen',
                    side_effect=[first, response(['Spirit\\V[900000]'], 'lab/second:free')]) as http:
                self.assertEqual(request_batch(['灵力\\V[900000]'], PROFILE, 'en', lambda: False), ['Spirit\\V[900000]'])
                self.assertEqual(http.call_count, 2)

    def test_daily_quota_stops_without_fallback_for_both_error_formats(self):
        payload = json.dumps({'error': {'code': 429, 'message': 'free-models-per-day quota reached'}}).encode()
        for via_http in (True, False):
            with self.subTest(via_http=via_http):
                error = urllib.error.HTTPError(PROFILE['endpoint'], 429, 'quota', {}, io.BytesIO(payload))
                with patch('translation.urllib.request.urlopen', side_effect=error if via_http else None,
                           return_value=io.BytesIO(payload)) as http:
                    with self.assertRaisesRegex(TranslationError, 'daily free quota'):
                        request_batch(['灵力'], PROFILE, 'en', lambda: False)
                    self.assertEqual(http.call_count, 1)

    def test_account_failure_never_tries_paid_model(self):
        with patch('translation.urllib.request.urlopen', return_value=io.BytesIO(b'{"error":{"code":402}}')) as http:
            with self.assertRaisesRegex(TranslationError, 'HTTP 402'):
                request_batch(['灵力'], PROFILE, 'en', lambda: False)
            self.assertEqual(http.call_count, 1)

    def test_completed_project_records_actual_model_and_resume_makes_no_calls(self):
        project = project_with_batches(1)
        def http(request, timeout):
            texts = json.loads(json.loads(request.data)['messages'][1]['content'])
            return response(translated(texts), 'lab/actual:free')
        with tempfile.TemporaryDirectory() as folder, patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.urllib.request.urlopen', http):
            result = translate(project, folder, concurrency=1)
            self.assertEqual(result['translated'], 12)
            saved = json.loads((Path(folder) / 'project.json').read_text(encoding='utf-8'))
            self.assertTrue(all(u['model'] == 'lab/actual:free' and u['engine'] == 'openrouter-free' for u in saved['units']))
            with patch('translation.request_batch') as request:
                self.assertEqual(translate(project, folder)['total'], 0)
                request.assert_not_called()


class FreeConfigurationTests(unittest.TestCase):
    def test_saved_mode_keeps_key_but_changes_profile_and_estimate(self):
        with patch('app_config.preferences', return_value={'translation_mode': 'free', 'minimum_intelligence': 32}), \
             patch('api_access.selected_key', return_value='sk-or-fixture'), patch('api_access.is_personal_key', return_value=True):
            profile = app_config.service_profile()
            self.assertTrue(profile['free_only'])
            self.assertEqual(profile['minimum_intelligence'], 32)
            estimate = estimate_project(project_with_batches(1))
            self.assertEqual(estimate['pence'], '0')
            self.assertEqual(format_pence(estimate), 'Free (0p)')
            self.assertFalse(app_config.service_profile(mode='paid').get('free_only', False))

    def test_free_mode_requires_openrouter_and_does_not_use_deepseek_key(self):
        with patch('app_config.preferences', return_value={'translation_mode': 'free'}), \
             patch('api_access.selected_key', return_value='deepseek-fixture'):
            with self.assertRaisesRegex(ValueError, 'OpenRouter key'):
                app_config.service_profile()

    def test_free_mode_exempts_friends_cost_cap(self):
        with patch('translation_cost.is_friends_build', return_value=True):
            enforce_translation_policy(project_with_batches(100), profile=PROFILE)

    def test_changing_preference_cannot_bypass_paid_shared_key_cap(self):
        with patch('translation_cost.is_friends_build', return_value=True), \
             patch('translation_cost.translation_mode', return_value='free'):
            with self.assertRaises(PermissionError):
                enforce_translation_policy(project_with_batches(1000), profile={'personal_key': False})


if __name__ == '__main__':
    unittest.main()
