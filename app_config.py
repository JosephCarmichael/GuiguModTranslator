"""Portable application paths and bundled service configuration."""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_DIR

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
    local = data_dir() / 'service.json'
    bundled = RESOURCE_DIR / 'bundled_service.json'
    path = local if local.is_file() else bundled
    if not path.is_file():
        raise ValueError('Translation access is not configured. Please obtain a configured copy of the app.')
    profile = json.loads(path.read_text(encoding='utf-8'))
    key = str(profile.get('api_key', '')).strip()
    if not key:
        raise ValueError('The translation key is missing. Please obtain an updated copy of the app.')
    if key.startswith('sk-or-'):
        return {'api_key': key, 'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
                'model': 'deepseek/deepseek-v4.1-flash', 'provider': 'OpenRouter'}
    return {'api_key': key, 'endpoint': 'https://api.deepseek.com/v1/chat/completions',
            'model': 'deepseek-flash', 'provider': 'DeepSeek'}

def installed_game():
    saved = data_dir() / 'preferences.json'
    candidates = []
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
