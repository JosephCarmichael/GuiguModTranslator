"""OpenRouter key allowance, reconciled with actual response charges.

No management key is requested. Unlimited keys need not expose an account
balance. GBP is an estimate; OpenRouter reports dollars/credits.
"""
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from app_config import data_dir


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = Decimal(str(value))
        return value if value.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def identity(profile):
    key = profile.get('api_key') if profile else None
    if not key or profile.get('provider') != 'OpenRouter':
        return None
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def fetch_key_info(profile):
    request = urllib.request.Request('https://openrouter.ai/api/v1/key',
        headers={'Authorization': 'Bearer ' + profile['api_key'], 'X-Title': 'Guigu Mod Translator'})
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
        value = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(value, dict) or 'limit_remaining' not in value:
        raise ValueError('OpenRouter did not provide key balance information.')
    return value


class BalanceTracker:
    def __init__(self, folder):
        self.path = folder / 'translation-balances.json'
        self.condition = threading.Condition()
        self.active = {}
        self.refreshing = set()
        try:
            cached = json.loads(self.path.read_text(encoding='utf-8'))
            self.states = cached if isinstance(cached, dict) else {}
        except (OSError, ValueError):
            self.states = {}

    def _state(self, ident):
        if not isinstance(self.states.get(ident), dict):
            self.states[ident] = {}
        return self.states[ident]

    def _save(self):
        from installer import atomic_bytes
        try:
            atomic_bytes(self.path, json.dumps(self.states).encode('utf-8'))
        except OSError:
            pass  # A balance-cache failure must not discard a translation.

    def snapshot(self, profile):
        ident = identity(profile)
        if not ident:
            return {'unsupported': True}
        with self.condition:
            return dict(self._state(ident))

    @contextmanager
    def request(self, profile):
        ident = identity(profile)
        if not ident:
            yield
            return
        with self.condition:
            while ident in self.refreshing:
                self.condition.wait()
            self.active[ident] = self.active.get(ident, 0) + 1
        try:
            yield
        finally:
            with self.condition:
                self.active[ident] -= 1
                self.condition.notify_all()

    def record_response(self, profile, response):
        ident = identity(profile)
        if not ident or not isinstance(response, dict):
            return
        usage = response.get('usage')
        cost = number(usage.get('cost')) if isinstance(usage, dict) else None
        if cost is None or cost < 0:
            return
        with self.condition:
            state = self._state(ident)
            generation = response.get('id')
            seen = state.get('seen', [])
            if not isinstance(seen, list):
                seen = []
            if generation and generation in seen:
                return
            if isinstance(generation, str):
                state['seen'] = (seen + [generation])[-512:]
            remaining = number(state.get('remaining_usd'))
            expected = number(state.get('expected_usage'))
            if remaining is not None:
                state['remaining_usd'] = str(max(Decimal(0), remaining - cost))
            if expected is not None:
                state['expected_usage'] = str(expected + cost)
            state['estimated'] = True
            state['last_charge_usd'] = str(cost)
            state['changed_at'] = time.time()
            self._save()

    def refresh(self, profile):
        ident = identity(profile)
        if not ident:
            return False
        with self.condition:
            if self.active.get(ident) or ident in self.refreshing:
                return False
            self.refreshing.add(ident)
        try:
            data = fetch_key_info(profile)
            remaining = number(data.get('limit_remaining'))
            usage = number(data.get('usage'))
            limit = number(data.get('limit'))
            if data.get('limit_remaining') is not None and remaining is None:
                raise ValueError('OpenRouter returned an invalid balance.')
            with self.condition:
                state = self._state(ident)
                expected = number(state.get('expected_usage'))
                old_usage = number(state.get('reported_usage'))
                old_remaining = number(state.get('remaining_usd'))
                # Some usage endpoints lag the completion response. Do not put
                # already charged money back until the usage total catches up.
                stale = (remaining is not None and usage is not None and expected is not None
                         and old_remaining is not None and number(state.get('limit')) == limit
                         and usage < expected and (old_usage is None or usage >= old_usage))
                if stale:
                    remaining = min(remaining, old_remaining)
                else:
                    state['expected_usage'] = str(usage) if usage is not None else None
                state.update(remaining_usd=str(max(Decimal(0), remaining)) if remaining is not None else None,
                             reported_usage=str(usage) if usage is not None else None,
                             limit=str(limit) if limit is not None else None,
                             estimated=stale, checked_at=time.time(), error=None)
                self._save()
            return True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            code = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            with self.condition:
                self._state(ident)['error'] = ('Could not refresh balance' + (f' (HTTP {code})' if code else '') + '.')
            return False
        finally:
            with self.condition:
                self.refreshing.discard(ident)
                self.condition.notify_all()


_trackers = {}
_lock = threading.Lock()


def tracker():
    folder = data_dir()
    with _lock:
        if str(folder) not in _trackers:
            _trackers[str(folder)] = BalanceTracker(folder)
        return _trackers[str(folder)]


def balance_text(state):
    from translation_cost import USD_TO_GBP
    value = number(state.get('remaining_usd'))
    if state.get('unsupported'):
        return 'Balance: unavailable', 'Choose an OpenRouter key to check its remaining allowance.'
    if value is None:
        if state.get('error'):
            return 'Balance: unavailable', state['error']
        if state.get('checked_at'):
            return 'Balance: not provided', 'OpenRouter does not expose a balance for this unlimited key.'
        return 'Balance: checking…', 'Reading your remaining OpenRouter key allowance…'
    pence = (value * USD_TO_GBP * 100).quantize(Decimal('.01'), rounding=ROUND_DOWN)
    display = ('£' + format(pence / 100, '.2f')) if pence >= 100 else format(pence, '.2f') + 'p'
    detail = 'OpenRouter key: $' + format(value, '.4f') + ' remaining · GBP estimate'
    if state.get('error'):
        detail += ' · last known'
    return 'Balance: ~' + display, detail
