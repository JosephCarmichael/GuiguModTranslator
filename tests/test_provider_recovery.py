import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from translation import RequestGate, request_batch, translate, TranslationError, retry_delay
from test_parallel_translation import PROFILE, project_with_batches, translated


class ProviderRecoveryTests(unittest.TestCase):
    def test_server_errors_recover_after_more_than_three_attempts(self):
        attempts = []
        gate = RequestGate(16)
        def http(request, timeout):
            attempts.append(1)
            if len(attempts) <= 4:
                raise urllib.error.HTTPError(request.full_url, 503, 'Unavailable', {'Retry-After': '0'}, None)
            return io.BytesIO(b'{"choices":[{"message":{"content":"[\\"Spirit\\"]"}}]}')
        with patch('translation.urllib.request.urlopen', http):
            self.assertEqual(request_batch(['灵力'], PROFILE, 'en', lambda: False, gate=gate), ['Spirit'])
        self.assertEqual(len(attempts), 5)
        self.assertLess(gate.limit, 16)
        self.assertEqual(gate.active, 0)

    def test_http_200_provider_error_is_retried(self):
        responses = [b'{"error":{"code":429}}', b'{"choices":[{"message":{"content":"[\\"Spirit\\"]"}}]}']
        with patch('translation.urllib.request.urlopen', side_effect=lambda *_a, **_k: io.BytesIO(responses.pop(0))), \
             patch('translation.retry_delay', return_value=0):
            self.assertEqual(request_batch(['灵力'], PROFILE, 'en', lambda: False), ['Spirit'])
        self.assertFalse(responses)

    def test_account_errors_stop_immediately_and_identify_status(self):
        for status in (401, 402, 403):
            with self.subTest(status=status):
                body = json.dumps({'error': {'code': status}}).encode()
                with patch('translation.urllib.request.urlopen', return_value=io.BytesIO(body)) as http:
                    with self.assertRaisesRegex(TranslationError, 'HTTP '+str(status)):
                        request_batch(['灵力'], PROFILE, 'en', lambda: False)
                self.assertEqual(http.call_count, 1)

    def test_actual_http_admission_follows_reduced_limit(self):
        gate = RequestGate(16)
        gate.recover(429, 0, 1)
        self.assertEqual(gate.limit, 8)
        gate.spacing = 0
        for _ in range(8):
            gate.acquire(lambda: False)
        admitted = threading.Event()
        def waiter():
            gate.acquire(lambda: False)
            admitted.set()
            gate.release()
        worker = threading.Thread(target=waiter)
        worker.start()
        try:
            self.assertFalse(admitted.wait(0.05))
            gate.release()
            self.assertTrue(admitted.wait(1))
        finally:
            for _ in range(7):
                gate.release()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(gate.active, 0)

    def test_error_wave_reduces_once_then_recovers_gradually(self):
        gate = RequestGate(16)
        with patch('translation.time.monotonic', return_value=100):
            for _ in range(16):
                gate.recover(500, 5, 1)
        self.assertEqual(gate.limit, 8)
        with patch('translation.time.monotonic', return_value=131):
            for _ in range(32):
                gate.succeeded()
        self.assertEqual(gate.limit, 9)

    def test_countdown_includes_real_status_and_is_cancellable(self):
        gate = RequestGate(16)
        gate.recover(500, 60, 1)
        text = gate.status()
        self.assertIn('HTTP 500', text)
        self.assertIn('using 8 of 16', text)
        self.assertIn('retrying in', text)
        with self.assertRaises(InterruptedError):
            gate.acquire(lambda: True)

    def test_diagnostic_log_and_saved_translations_after_recovery(self):
        project = project_with_batches(1)
        calls = []
        def http(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 500, 'Internal error', {'Retry-After': '0'}, None)
            texts = json.loads(json.loads(request.data)['messages'][1]['content'])
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(translated(texts))}}]}).encode())
        with tempfile.TemporaryDirectory() as directory:
            with patch('translation.service_profile', return_value=PROFILE), patch('translation.urllib.request.urlopen', http):
                result = translate(project, directory, batch_size=12, concurrency=16)
            self.assertEqual(result['translated'], 12)
            event = json.loads((Path(directory)/'request-errors.jsonl').read_text())
            self.assertEqual(event['code'], 500)
            self.assertEqual(event['provider'], 'DeepSeek')
            self.assertEqual(event['active_limit'], 8)
            self.assertNotIn('api_key', event)
            self.assertNotIn('source', event)

    def test_persistent_failure_has_bounded_retries_and_precise_error(self):
        def http(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 502, 'Upstream error', {'Retry-After': '0'}, None)
        gate = RequestGate()
        with patch('translation.urllib.request.urlopen', side_effect=http) as request, \
             patch('translation.random.uniform', return_value=0):
            with self.assertRaisesRegex(TranslationError, 'HTTP 502.*8 attempts'):
                request_batch(['灵力'], PROFILE, 'en', lambda: False, gate=gate)
        self.assertEqual(request.call_count, 8)
        self.assertEqual(gate.active, 0)

    def test_backoff_waits_longer_and_caps(self):
        with patch('translation.random.uniform', return_value=0):
            self.assertEqual([retry_delay(None, i) for i in range(8)], [5, 10, 20, 40, 60, 60, 60, 60])


if __name__ == '__main__':
    unittest.main()
