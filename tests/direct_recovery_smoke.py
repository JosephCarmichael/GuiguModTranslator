"""Explicit bounded live check on a copy of the user's real untranslated mod text."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    app = Path(os.environ['LOCALAPPDATA'])/'GuiguModTranslator'
    os.environ['GUIGU_TRANSLATOR_DATA'] = str(app)
    from app_config import service_profile
    import translation
    profile = service_profile()
    source = app/'projects/2814696167/project.json'
    project = json.loads(source.read_text(encoding='utf-8'))
    project['units'] = [u for u in project['units'] if not u['translation'] and u['category'] != 'technical'][:192]
    folder = ROOT/'projects/direct-recovery-smoke'
    folder.mkdir(parents=True, exist_ok=True)
    attempts = []
    lock = threading.Lock()
    original = translation.urllib.request.urlopen
    active = peak = 0
    def measured(request, timeout):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            with original(request, timeout=timeout) as response:
                import io
                value = response.read()
                with lock:
                    attempts.append(response.status)
                return io.BytesIO(value)
        except translation.urllib.error.HTTPError as exc:
            with lock:
                attempts.append(exc.code)
            raise
        finally:
            with lock:
                active -= 1
    start = time.monotonic()
    report = {'provider': profile['provider'], 'model': profile['model'], 'requested_concurrency': 16,
              'mod': project['mod']['id'], 'entries': len(project['units']),
              'source_characters': sum(len(u['source']) for u in project['units'])}
    try:
        with patch('translation.urllib.request.urlopen', measured):
            result = translation.translate(project, folder, batch_size=12, concurrency=16, include_review=True,
                                           stop=lambda: time.monotonic()-start > 90)
        report.update(result=result, completed=not result['cancelled'])
    except Exception as exc:
        report.update(error=str(exc), completed=False)
    report.update(http_statuses=attempts, peak_http_requests=peak, elapsed_seconds=round(time.monotonic()-start, 3))
    (ROOT/'projects/direct-recovery-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
