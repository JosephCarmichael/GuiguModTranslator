"""English mod titles, translated once and saved for later launches."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app_config import data_dir
from extractor import CJK, atomic_json, validate_translation

TITLE_FILE = 'mod-titles.json'
TITLE_BATCH = 24


def validate_title(source, title):
    if not isinstance(title, str) or not title.strip() or CJK.search(title) or title == source:
        return 'An English title is required'
    # Metadata commonly starts with [author]. Translating a Chinese author to
    # [English] must not manufacture a runtime placeholder in the validator.
    if re.match(r'^\[[^\[\]\r\n]+\]', source):
        source = re.sub(r'^\[([^\[\]\r\n]+)\]', r'(\1)', source)
        title = re.sub(r'^\[([^\[\]\r\n]+)\]', r'(\1)', title)
    return validate_translation(source, title)


def titles_path():
    return data_dir() / TITLE_FILE


def load_titles():
    """Saved titles: {mod id: {'source': Chinese name, 'title': English}}."""
    try:
        value = json.loads(titles_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    saved = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        source, title = item.get('source'), item.get('title')
        if isinstance(source, str) and source.strip() and not validate_title(source, title):
            saved[str(key)] = {'source': source, 'title': title.strip()}
    return saved


def save_titles(titles):
    atomic_json(titles_path(), titles)


def saved_title(titles, mod):
    """Reuse a saved title only while the mod still carries the same name."""
    item = titles.get(str(mod.get('id')))
    return item['title'] if item and item.get('source') == mod.get('name') else None


def record(titles, mod, title):
    titles[str(mod['id'])] = {'source': str(mod.get('name', '')), 'title': title}
    return titles


def apply_titles(mods, titles):
    """Attach the saved title to each mod that already has one."""
    for mod in mods:
        title = saved_title(titles, mod)
        if title:
            mod['title'] = title
        else:
            mod.pop('title', None)
    return mods


def display_name(mod, titles=None):
    """English title first, with the original Chinese name kept on the row."""
    name = str(mod.get('name', '')).strip()
    title = str(mod.get('title') or (saved_title(titles, mod) if titles else '') or '').strip()
    return f'{title} ({name})' if title and title != name else name


def needs_title(mod, titles):
    name = str(mod.get('name', '')).strip()
    return bool(name) and bool(CJK.search(name)) and saved_title(titles, mod) is None


def translate_titles(mods, titles, progress=None, stop=None, on_save=None, retranslate=False):
    """Translate every unknown Chinese mod name once, then save the results.

    No request is made for names that are already saved, already English, or
    unchanged since the last launch. A provider problem never stops the app:
    the Chinese name stays in the list and the next launch tries again.
    """
    stop = stop or (lambda: False)
    progress = progress or (lambda _: None)
    on_save = on_save or (lambda _: None)
    pending = [mod for mod in mods if needs_title(mod, {} if retranslate else titles)]
    result = {'translated': 0, 'failed': 0, 'pending': len(pending), 'saved': len(titles),
              'cancelled': False, 'error': ''}
    if not pending:
        return result
    from app_config import service_profile
    from translation import RequestGate, request_batch
    try:
        profile = service_profile()
    except (OSError, ValueError) as exc:
        result['error'] = str(exc)
        return result
    gate = RequestGate(1)
    for start in range(0, len(pending), TITLE_BATCH):
        if stop():
            result['cancelled'] = True
            break
        chunk = pending[start:start + TITLE_BATCH]
        progress(f'Translating mod titles… {start + len(chunk)} of {len(pending)}')
        try:
            values = request_batch([str(mod.get('name', '')) for mod in chunk], profile, 'en', stop, gate=gate)
        except InterruptedError:
            result['cancelled'] = True
            break
        except Exception as exc:
            # A failed batch keeps the remaining names untranslated for retry.
            result['error'] = str(exc)
            result['failed'] += len(chunk)
            break
        for mod, value in zip(chunk, values):
            title = value.strip() if isinstance(value, str) else value
            if validate_title(str(mod.get('name', '')), title):
                result['failed'] += 1
                continue
            record(titles, mod, title)
            result['translated'] += 1
        save_titles(titles)
        on_save(dict(titles))
    result['saved'] = len(titles)
    return result
