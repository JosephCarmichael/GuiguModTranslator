"""Portable application paths and bundled service configuration."""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
APP_VERSION = '1.4.0'
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_DIR
CONCURRENCY_CHOICES = (1, 4, 8, 16, 32, 64, 128)
DEFAULT_CONCURRENCY = 16
BATCH_SIZE_CHOICES = (12, 24, 48, 96)
DEFAULT_BATCH_SIZE = 48


def is_friends_build():
    if not getattr(sys, 'frozen', False):
        return False
    try:
        policy = json.loads((RESOURCE_DIR / 'build_policy.json').read_text(encoding='utf-8'))
        return policy.get('edition') != 'personal'
    except (OSError, ValueError, AttributeError):
        # A frozen build with missing/invalid policy never gains personal access.
        return True


def preferences():
    try:
        value = json.loads((data_dir() / 'preferences.json').read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def translation_concurrency():
    value = preferences().get('concurrency', DEFAULT_CONCURRENCY)
    return value if type(value) is int and value in CONCURRENCY_CHOICES else DEFAULT_CONCURRENCY


def translation_batch_size():
    value = preferences().get('batch_size', DEFAULT_BATCH_SIZE)
    return value if type(value) is int and value in BATCH_SIZE_CHOICES else DEFAULT_BATCH_SIZE


def bulk_price_pence():
    value = preferences().get('bulk_price_pence', 5)
    return value if type(value) is int and 5 <= value <= 200 else 5


def save_preferences(**changes):
    from extractor import atomic_json
    value = preferences()
    value.update(changes)
    atomic_json(data_dir() / 'preferences.json', value)

def data_dir():
    override = os.environ.get('GUIGU_TRANSLATOR_DATA')
    if override:
        result = Path(override)
    elif not getattr(sys, 'frozen', False):
        result = APP_DIR
    else:
        result = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GuiguModTranslator'
    result.mkdir(parents=True, exist_ok=True)
    return result

def service_profile():
    from api_access import selected_key, is_personal_key
    selected = selected_key()
    local = data_dir() / 'service.json'
    bundled = RESOURCE_DIR / 'bundled_service.json'
    path = local if local.is_file() else bundled
    if selected is None:
        if not path.is_file():
            raise ValueError('Translation access is not configured. Please obtain a configured copy of the app.')
        profile = json.loads(path.read_text(encoding='utf-8'))
        key = str(profile.get('api_key', '')).strip()
    else:
        key = selected
    if not key:
        raise ValueError('The translation key is missing. Please obtain an updated copy of the app.')
    if key.startswith('sk-or-'):
        return {'api_key': key, 'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
                'model': 'deepseek/deepseek-v4.1-flash', 'provider': 'OpenRouter',
                'personal_key': is_personal_key(key)}
    return {'api_key': key, 'endpoint': 'https://api.deepseek.com/v1/chat/completions',
            'model': 'deepseek-flash', 'provider': 'DeepSeek'}

def installed_game():
    saved = data_dir() / 'preferences.json'
    candidates = []
    pending_repair = data_dir() / 'launch-repair-pending.json'
    if pending_repair.is_file():
        try:
            repair = json.loads(pending_repair.read_text(encoding='utf-8'))
            candidates.extend(Path(repair[key]) for key in ('target', 'source'))
        except (ValueError, OSError, KeyError, TypeError):
            pass
    if saved.is_file():
        try:
            candidates.append(Path(json.loads(saved.read_text(encoding='utf-8')).get('game', '')))
        except (ValueError, OSError):
            pass
    candidates.extend([APP_DIR, APP_DIR.parent, APP_DIR.parent.parent])
    steam_roots = []
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                steam_roots.append(Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
        except OSError:
            pass
        steam_roots.append(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam')
    else:
        steam_roots.append(Path('/mnt/c/Program Files (x86)/Steam'))
    libraries = list(steam_roots)
    for root in steam_roots:
        manifest = root / 'steamapps/libraryfolders.vdf'
        if manifest.is_file():
            text = manifest.read_text(encoding='utf-8', errors='replace')
            libraries.extend(Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s*"([^"]+)"', text))
    for root in libraries:
        apps = root / 'steamapps'
        manifest = apps / 'appmanifest_1468810.acf'
        if manifest.is_file():
            match = re.search(r'"installdir"\s*"([^"]+)"', manifest.read_text(encoding='utf-8', errors='replace'))
            if match:
                candidates.append(apps / 'common' / match.group(1))
        candidates.extend(apps / 'common' / name for name in ('TaleOfImmortal', '鬼谷八荒', 'Tale of Immortal'))
    return next((p for p in candidates if (p / 'guigubahuang.exe').is_file()), None)
