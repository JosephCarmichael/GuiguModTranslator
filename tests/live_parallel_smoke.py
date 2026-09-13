"""Explicit live check: 16 batches of 12 short strings through the shared profile."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='Guigu Parallel Live ') as directory:
        # Test the same shared profile shipped in the executable, without logging it.
        with patch.dict(os.environ, {'GUIGU_TRANSLATOR_DATA': directory}):
            import translation
            from app_config import service_profile
            profile = service_profile()
            project = {'mod': {'id': 'parallel-live'}, 'coverage': {'files': []}, 'units': [
                {'id': str(i), 'source': f'灵力 {i} {{0}}', 'translation': '', 'status': 'untranslated',
                 'category': 'player_text', 'occurrences': []} for i in range(192)]}
            original = translation.urllib.request.urlopen
            lock = threading.Lock()
            active = peak = calls = 0
            def measured(request, timeout):
                nonlocal active, peak, calls
                with lock:
                    active += 1
                    calls += 1
                    peak = max(peak, active)
                try:
                    # Hold the count through the actual response body read.
                    response = original(request, timeout=timeout)
                    import io
                    with response:
                        return io.BytesIO(response.read())
                finally:
                    with lock:
                        active -= 1
            start = time.monotonic()
            report = {'provider': profile['provider'], 'model': profile['model'], 'requested_concurrency': 16}
            try:
                with patch('translation.urllib.request.urlopen', measured):
                    result = translation.translate(project, Path(directory)/'project', batch_size=12, concurrency=16)
                report.update(result=result, passed=result['translated'] == 192 and result['failed'] == 0 and peak == 16)
            except Exception as exc:
                report.update(passed=False, error=str(exc))
            report.update(peak_http_requests=peak, http_attempts=calls, elapsed_seconds=round(time.monotonic()-start, 3))
            target = ROOT/'projects/parallel-live-check.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2), flush=True)
            if not report['passed']:
                raise SystemExit(1)


if __name__ == '__main__':
    main()
