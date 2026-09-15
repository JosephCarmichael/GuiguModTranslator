import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from translation_balance import BalanceTracker, balance_text, fetch_key_info
from translation import request_batch

PROFILE = {'provider': 'OpenRouter', 'api_key': 'sk-or-v1-balance-fixture-key',
           'endpoint': 'https://example.invalid/chat/completions', 'model': 'fixture'}


class BalanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.balance = BalanceTracker(self.folder)
        self.refresh('.57', '.43')

    def refresh(self, remaining, usage, limit='1'):
        with patch('translation_balance.fetch_key_info', return_value={
                'limit_remaining': remaining, 'usage': usage, 'limit': limit}):
            self.assertTrue(self.balance.refresh(PROFILE))

    def cost(self, cost='.01', ident='generation-1'):
        self.balance.record_response(PROFILE, {'id': ident, 'usage': {'cost': cost}})

    def remaining(self):
        return Decimal(self.balance.snapshot(PROFILE)['remaining_usd'])

    def test_confirmed_charge_decreases_balance_and_duplicate_id_is_not_charged_twice(self):
        self.cost()
        self.assertEqual(self.remaining(), Decimal('.56'))
        self.cost()
        self.assertEqual(self.remaining(), Decimal('.56'))
        self.assertNotIn(PROFILE['api_key'], self.balance.path.read_text())

    def test_live_refresh_reconciles_without_double_subtraction(self):
        self.cost()
        self.refresh('.56', '.44')
        self.assertEqual(self.remaining(), Decimal('.56'))
        self.assertFalse(self.balance.snapshot(PROFILE)['estimated'])

    def test_delayed_server_usage_does_not_put_spent_credit_back(self):
        self.cost()
        self.refresh('.57', '.43')
        self.assertEqual(self.remaining(), Decimal('.56'))
        self.assertTrue(self.balance.snapshot(PROFILE)['estimated'])
        self.refresh('.56', '.44')
        self.assertFalse(self.balance.snapshot(PROFILE)['estimated'])

    def test_spend_by_another_friend_is_reflected_on_refresh(self):
        self.cost()
        self.refresh('.50', '.50')
        self.assertEqual(self.remaining(), Decimal('.50'))

    def test_limit_increase_and_provider_usage_reset_can_raise_balance(self):
        self.cost()
        self.refresh('1.56', '.44', limit='2')
        self.assertEqual(self.remaining(), Decimal('1.56'))
        self.refresh('1.9', '.1', limit='2')
        self.assertEqual(self.remaining(), Decimal('1.9'))

    def test_cache_survives_restart_and_is_separate_for_each_key(self):
        self.cost()
        restored = BalanceTracker(self.folder)
        self.assertEqual(restored.snapshot(PROFILE)['remaining_usd'], '0.56')
        other = {**PROFILE, 'api_key': 'different-key'}
        self.assertIsNone(restored.snapshot(other).get('remaining_usd'))

    def test_unknown_unlimited_key_is_not_displayed_as_free_or_zero(self):
        self.refresh(None, '4', limit=None)
        label, detail = balance_text(self.balance.snapshot(PROFILE))
        self.assertEqual(label, 'Balance: not provided')
        self.assertIn('unlimited key', detail)

    def test_display_converts_dollars_to_pence_instead_of_labelling_cents_as_pence(self):
        label, detail = balance_text(self.balance.snapshot(PROFILE))
        self.assertTrue(label.startswith('Balance: ~42.'))
        self.assertIn('$0.5700', detail)
        self.assertNotIn('57p', label)

    def test_failed_refresh_preserves_balance_and_marks_it_last_known(self):
        with patch('translation_balance.fetch_key_info', side_effect=urllib.error.HTTPError('url', 401, 'secret response', {}, None)):
            self.assertFalse(self.balance.refresh(PROFILE))
        label, detail = balance_text(self.balance.snapshot(PROFILE))
        self.assertIn('last known', detail)
        self.assertNotIn('secret', str(self.balance.snapshot(PROFILE)))
        self.assertEqual(self.remaining(), Decimal('.57'))

    def test_parallel_confirmations_are_counted_exactly(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(lambda i: self.cost('.001', 'gen-'+str(i)), range(128)))
        self.assertEqual(self.remaining(), Decimal('.442'))

    def test_refresh_waits_until_requests_finish(self):
        with self.balance.request(PROFILE), patch('translation_balance.fetch_key_info') as fetch:
            self.assertFalse(self.balance.refresh(PROFILE))
            fetch.assert_not_called()

    def test_request_waits_for_refresh_to_prevent_counting_same_charge_twice(self):
        entered, release, sending = threading.Event(), threading.Event(), threading.Event()
        def fetch(profile):
            entered.set()
            self.assertTrue(release.wait(5))
            return {'limit': 1, 'limit_remaining': '.57', 'usage': '.43'}
        def send():
            with self.balance.request(PROFILE):
                sending.set(); self.cost()
        with patch('translation_balance.fetch_key_info', side_effect=fetch), ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(self.balance.refresh, PROFILE)
            self.assertTrue(entered.wait(5))
            request = pool.submit(send)
            self.assertFalse(sending.wait(.05))
            release.set(); reading.result(5); request.result(5)
        self.assertEqual(self.remaining(), Decimal('.56'))

    def test_billable_invalid_response_and_successful_retry_both_reduce_balance(self):
        replies = [
            {'id': 'invalid-billed', 'usage': {'cost': '.01'}, 'choices': [{'message': {'content': 'not json'}}]},
            {'id': 'valid-billed', 'usage': {'cost': '.02'}, 'choices': [{'message': {'content': '["Spirit"]'}}]}]
        with patch('translation_balance.tracker', return_value=self.balance), \
             patch('translation.urllib.request.urlopen', side_effect=[io.BytesIO(json.dumps(r).encode()) for r in replies]), \
             patch('translation.retry_delay', return_value=0):
            self.assertEqual(request_batch(['灵力'], PROFILE, 'en', lambda: False), ['Spirit'])
        self.assertEqual(self.remaining(), Decimal('.54'))

    def test_missing_or_invalid_cost_is_not_guessed_and_balance_cannot_be_negative(self):
        for cost in (None, 'NaN', '-1', 'invalid'):
            self.cost(cost, str(cost))
        self.assertEqual(self.remaining(), Decimal('.57'))
        self.cost('1', 'larger-than-remaining')
        self.assertEqual(self.remaining(), Decimal(0))

    def test_read_only_request_uses_only_current_key_endpoint(self):
        with patch('translation_balance.urllib.request.urlopen', return_value=io.BytesIO(b'{"data":{"limit_remaining":0.57}}')) as call:
            fetch_key_info(PROFILE)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, 'https://openrouter.ai/api/v1/key')
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.get_header('Authorization'), 'Bearer '+PROFILE['api_key'])


if __name__ == '__main__': unittest.main()
