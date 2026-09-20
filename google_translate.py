"""Optional, unauthenticated Google web translation with conservative pacing."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from extractor import CJK, TOKENS

ENDPOINT = 'https://translate.googleapis.com/translate_a/single'
MAX_CHARS = 700
REQUEST_SPACING = 1.0
_lock = threading.Lock()
_next_start = 0.0


def fetch(text, target, stop, gate=None):
    from translation import TranslationError
    global _next_start
    # Titles and mod jobs share one limiter. No parallel web requests, proxy
    # rotation, authentication, or fallback to a chargeable provider.
    while not _lock.acquire(timeout=0.1):
        if stop():
            raise InterruptedError('Translation cancelled')
    try:
        while time.monotonic() < _next_start:
            if stop():
                raise InterruptedError('Translation cancelled')
            time.sleep(min(0.1, max(0, _next_start - time.monotonic())))
        if stop():
            raise InterruptedError('Translation cancelled')
        _next_start = time.monotonic() + REQUEST_SPACING
        query = urllib.parse.urlencode({'client': 'gtx', 'sl': 'zh-CN',
                                       'tl': 'en' if target.lower() == 'english' else target,
                                       'dt': 't', 'q': text})
        request = urllib.request.Request(ENDPOINT + '?' + query,
                                         headers={'User-Agent': 'GuiguModTranslator'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Oversized response')
            payload = json.loads(raw)
            rows = payload[0]
            if not isinstance(rows, list) or not rows:
                raise ValueError('Missing translated sentences')
            values = []
            for row in rows:
                if not isinstance(row, list) or not row or not isinstance(row[0], str):
                    raise ValueError('Invalid translated sentence')
                values.append(row[0])
            result = ''.join(values).strip()
            if not result or (target.lower() in ('en', 'english') and CJK.search(result)):
                raise ValueError('Incomplete translation')
            return result
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code in (403, 429):
                _next_start = time.monotonic() + 60
            if gate is not None:
                gate.events.put({'code': code, 'reason': 'Google web request rejected', 'terminal': True})
            raise TranslationError(f'Google Translate HTTP {code}: the web service is unavailable or throttled. '
                                   'Progress is saved. Resume later or choose another provider.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TranslationError('Google Translate could not be reached. Progress is saved; resume later.') from None
        except (ValueError, IndexError, KeyError, TypeError):
            raise TranslationError('Google Translate returned an incomplete or unsupported response. '
                                   'Progress is saved; choose another provider or retry later.') from None
    finally:
        _lock.release()


def translate_text(text, target, stop, glossary=None, gate=None):
    # Keep formatting tokens, exact newlines, numbers and glossary substitutions
    # out of the web request. The project pipeline validates tokens again.
    terms = {k: v for k, v in (glossary or {}).items()
             if isinstance(k, str) and k and isinstance(v, str) and v}
    pattern = TOKENS.pattern + r'|\r\n|[\r\n]|\d+(?:\.\d+)?'
    if terms:
        pattern += '|' + '|'.join(re.escape(k) for k in sorted(terms, key=len, reverse=True))
    protected = re.compile(pattern)
    output = []

    def append_plain(value):
        for start in range(0, len(value), MAX_CHARS):
            chunk = value[start:start + MAX_CHARS]
            if not CJK.search(chunk):
                output.append(chunk)
                continue
            leading = chunk[:len(chunk) - len(chunk.lstrip())]
            trailing = chunk[len(chunk.rstrip()):]
            translated = fetch(chunk.strip(), target, stop, gate)
            if output and output[-1] and output[-1][-1].isalnum() and translated[0].isalnum() and not leading:
                leading = ' '
            output.append(leading + translated + trailing)

    cursor = 0
    for match in protected.finditer(text):
        append_plain(text[cursor:match.start()])
        token = match.group()
        value = terms.get(token, token)
        if token in terms and output and output[-1] and (output[-1][-1].isalnum() or output[-1].endswith('%')) and value[0].isalnum():
            value = ' ' + value
        output.append(value)
        cursor = match.end()
    append_plain(text[cursor:])
    return ''.join(output)


def request_batch(texts, target, stop, glossary=None, gate=None):
    results = []
    for text in texts:
        if stop():
            raise InterruptedError('Translation cancelled')
        results.append(translate_text(text, target, stop, glossary, gate))
    return results
