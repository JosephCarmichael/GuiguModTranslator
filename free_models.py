"""Live, scored OpenRouter free models and account-wide request pacing."""
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

CATALOG_URL = 'https://openrouter.ai/api/v1/models'
CACHE_SECONDS = 600
REQUEST_SPACING = 3.1  # At most 20 starts/minute across titles and mod jobs.
_lock = threading.Lock()
_catalog = None
_checked = 0
_accounts = {}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def select_models(rows, minimum):
    floor = number(minimum)
    if floor is None or not 0 <= floor <= 100:
        raise ValueError('Minimum intelligence must be between 0 and 100.')
    selected = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = row.get('id', '')
        # Routers can silently select an unscored model; use concrete variants.
        if not isinstance(ident, str) or not ident.endswith(':free') or ident.startswith('openrouter/'):
            continue
        pricing = row.get('pricing') or {}
        if not isinstance(pricing, dict) or any(number(pricing.get(k)) != 0 for k in ('prompt', 'completion')):
            continue
        if any(number(v) != 0 for v in pricing.values()):
            continue  # Reject additional fees and unknown prices too.
        arch = row.get('architecture') or {}
        if not isinstance(arch, dict) or 'text' not in arch.get('input_modalities', []) or 'text' not in arch.get('output_modalities', []):
            continue
        benchmarks = row.get('benchmarks') or {}
        aa = benchmarks.get('artificial_analysis') if isinstance(benchmarks, dict) else None
        score = number(aa.get('intelligence_index')) if isinstance(aa, dict) else None
        if score is None or score < floor:
            continue
        context = number(row.get('context_length'))
        provider = row.get('top_provider') or {}
        output = number(provider.get('max_completion_tokens')) if isinstance(provider, dict) else None
        if context is None or context < 16384 or (output is not None and output < 8192):
            continue
        selected[ident] = {'id': ident, 'name': row.get('name') or ident,
                           'intelligence': float(score)}
    return sorted(selected.values(), key=lambda m: (-m['intelligence'], m['id']))


def discover(minimum=30, refresh=False):
    global _catalog, _checked
    # A single fetch serves concurrent title and translation workers. Never use
    # expired prices when refreshing fails, and never write credentials to disk.
    with _lock:
        if refresh or _catalog is None or time.monotonic() - _checked >= CACHE_SECONDS:
            try:
                request = urllib.request.Request(CATALOG_URL, headers={'X-Title': 'Guigu Mod Translator'})
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                rows = payload.get('data') if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    raise ValueError('Invalid model catalogue')
            except (OSError, ValueError) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                raise ValueError('Could not verify current free models and intelligence scores. Retry later; no paid fallback was used.') from None
            _catalog, _checked = rows, time.monotonic()
        models = select_models(_catalog, minimum)
    if not models:
        raise ValueError(f'No verified free text models meet intelligence {minimum:g} and the request limits. Lower the cutoff or retry later. Unscored models are excluded.')
    return models


class FreeAccount:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_start = 0
        self.cursor = 0

    def order(self, models):
        with self.lock:
            index = self.cursor % len(models)
            self.cursor += 1
        return models[index:] + models[:index]

    def defer(self, seconds):
        with self.lock:
            self.next_start = max(self.next_start, time.monotonic() + seconds)

    def acquire(self, stop):
        while True:
            if stop():
                raise InterruptedError('Translation cancelled')
            with self.lock:
                remaining = self.next_start - time.monotonic()
                if remaining <= 0:
                    self.next_start = time.monotonic() + REQUEST_SPACING
                    return
            time.sleep(min(0.1, remaining))


def account(profile):
    ident = hashlib.sha256(profile['api_key'].encode()).hexdigest()
    with _lock:
        return _accounts.setdefault(ident, FreeAccount())


def daily_limit(error):
    """Recognize daily quota errors without persisting provider response text."""
    message = str(error.get('message', '')).lower() if isinstance(error, dict) else ''
    return any(word in message for word in ('daily', 'per-day', 'per day'))
