"""Concurrency, response ownership and shutdown tests; no paid API calls."""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_config
from extractor import save_project, read_json
from translation import translate, request_batch, retry_delay, RequestGate, TranslationError

PROFILE = {'provider': 'DeepSeek', 'model': 'test-model', 'api_key': 'test',
           'endpoint': 'https://example.invalid/chat/completions'}


def project_with_batches(count):
    return {'mod': {'id': 'parallel-test', 'name': 'Test'}, 'coverage': {'files': []},
            'units': [{'id': str(i), 'source': f'灵力{i} {{0}}', 'translation': '',
                       'status': 'untranslated', 'category': 'player_text', 'occurrences': []}
                      for i in range(count * 12)]}


def translated(texts):
    return [s.replace('灵力', 'Spirit ') for s in texts]


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        profile = patch('translation.service_profile', return_value=PROFILE)
        profile.start()
        self.addCleanup(profile.stop)

    def test_selected_limits_are_reached_and_never_exceeded(self):
        for workers in (1, 16, 32, 64, 128):
            with self.subTest(workers=workers):
                project = project_with_batches(workers * 2)
                barrier = threading.Barrier(workers, timeout=10)
                lock = threading.Lock()
                active = peak = calls = 0
                writer_threads = set()
                owner = threading.get_ident()

                def http(request, timeout):
                    nonlocal active, peak, calls
                    with lock:
                        active += 1
                        calls += 1
                        peak = max(peak, active)
                    try:
                        barrier.wait()
                        texts = json.loads(json.loads(request.data)['messages'][1]['content'])
                        time.sleep(0.01)
                        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(translated(texts))}}]}).encode())
                    finally:
                        with lock:
                            active -= 1

                def checkpoint(p, folder):
                    writer_threads.add(threading.get_ident())
                    save_project(p, folder)

                with patch('translation.urllib.request.urlopen', http), patch('translation.save_project', checkpoint):
                    result = translate(project, self.folder, concurrency=workers)
                self.assertEqual(peak, workers)
                self.assertEqual(calls, workers * 2)
                self.assertEqual(result['translated'], workers * 24)
                self.assertEqual(writer_threads, {owner})
                saved = read_json(self.folder / 'project.json')
                self.assertTrue(all(u['translation'] == u['source'].replace('灵力', 'Spirit ') for u in saved['units']))

    def test_out_of_order_batch_is_saved_before_slow_first_batch(self):
        project = project_with_batches(2)
        release_first = threading.Event()
        saved_second_first = []

        def request(texts, *_):
            if texts[0].startswith('灵力0 '):
                if not release_first.wait(3):
                    raise AssertionError('Coordinator blocked on the first batch')
            return translated(texts)

        def checkpoint(p, folder):
            if p['units'][12]['translation'] and not p['units'][0]['translation']:
                saved_second_first.append(True)
            save_project(p, folder)
            release_first.set()

        with patch('translation.request_batch', request), patch('translation.save_project', checkpoint):
            result = translate(project, self.folder, concurrency=4)
        self.assertEqual(result['translated'], 24)
        self.assertTrue(saved_second_first)

    def test_cancel_stops_dispatch_and_saves_inflight_results(self):
        project = project_with_batches(40)
        cancel = threading.Event()
        barrier = threading.Barrier(16, action=cancel.set, timeout=5)
        called = []

        def request(texts, *_):
            called.append(texts[0])
            barrier.wait()
            return translated(texts)

        with patch('translation.request_batch', request):
            result = translate(project, self.folder, concurrency=16, stop=cancel.is_set)
        self.assertTrue(result['cancelled'])
        self.assertEqual(len(called), 16)
        self.assertEqual(result['translated'], 192)
        saved = read_json(self.folder / 'project.json')
        self.assertEqual(sum(bool(u['translation']) for u in saved['units']), 192)
        # Resume skips all successful requests from the cancelled job.
        with patch('translation.request_batch', side_effect=lambda texts, *_: translated(texts)):
            resumed = translate(saved, self.folder, concurrency=32)
        self.assertEqual(resumed['total'], (40 - 16) * 12)

    def test_service_failure_drains_successes_without_more_dispatch(self):
        project = project_with_batches(40)
        barrier = threading.Barrier(16, timeout=5)
        called = []

        def request(texts, profile, target, stopped, *_):
            called.append(texts[0])
            barrier.wait()
            if texts[0].startswith('灵力0 '):
                raise TranslationError('Allowance exhausted')
            deadline = time.monotonic() + 3
            while not stopped() and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(stopped())
            return translated(texts)

        with patch('translation.request_batch', request):
            with self.assertRaisesRegex(TranslationError, 'Allowance exhausted'):
                translate(project, self.folder, concurrency=16)
        self.assertEqual(len(called), 16)
        saved = read_json(self.folder / 'project.json')
        self.assertEqual(sum(bool(u['translation']) for u in saved['units']), 180)
        self.assertFalse(saved['units'][0]['translation'])

    def test_cancel_before_dispatch_makes_no_calls(self):
        with patch('translation.request_batch') as request:
            result = translate(project_with_batches(20), self.folder, concurrency=64, stop=lambda: True)
        request.assert_not_called()
        self.assertTrue(result['cancelled'])

    def test_invalid_concurrency_is_rejected(self):
        for value in (0, -1, 3, 256, '16', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                translate(project_with_batches(1), self.folder, concurrency=value)

    def test_shared_cooldown_is_cancellable(self):
        gate = RequestGate()
        gate.defer(30)
        stop = threading.Event()
        timer = threading.Timer(0.05, stop.set)
        timer.start()
        try:
            start = time.monotonic()
            with self.assertRaises(InterruptedError):
                gate.wait(stop.is_set)
            self.assertLess(time.monotonic() - start, 1)
        finally:
            timer.cancel()

    def test_http_429_sets_shared_cooldown_and_retries(self):
        gate = RequestGate()
        calls = []
        def http(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, 'Busy', {'Retry-After': '0'}, None)
            return io.BytesIO(b'{"choices":[{"message":{"content":"[\\"Spirit\\"]"}}]}')
        with patch('translation.urllib.request.urlopen', http), patch.object(gate, 'defer', wraps=gate.defer) as defer:
            self.assertEqual(request_batch(['灵力'], PROFILE, 'en', lambda: False, gate=gate), ['Spirit'])
        defer.assert_called_once_with(0)
        self.assertEqual(len(calls), 2)

    def test_retry_after_seconds_date_and_invalid_headers(self):
        self.assertEqual(retry_delay({'Retry-After': '7'}, 0), 7)
        date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
        self.assertTrue(28 <= retry_delay({'Retry-After': date}, 0) <= 30)
        for invalid in ('bad', '-1', 'nan', 'inf'):
            with patch('translation.random.uniform', return_value=0.5):
                self.assertEqual(retry_delay({'Retry-After': invalid}, 2), 4.5)

    def test_preferences_keep_game_and_request_limit(self):
        with patch('app_config.data_dir', return_value=self.folder):
            self.assertEqual(app_config.translation_concurrency(), 16)
            app_config.save_preferences(game='game-path')
            app_config.save_preferences(concurrency=64)
            self.assertEqual(app_config.translation_concurrency(), 64)
            app_config.save_preferences(game='moved-game')
            self.assertEqual(app_config.preferences(), {'game': 'moved-game', 'concurrency': 64})
            app_config.save_preferences(concurrency='invalid')
            self.assertEqual(app_config.translation_concurrency(), 16)


if __name__ == '__main__':
    unittest.main()
