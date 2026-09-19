"""Small, per-mod translation files in Git; exact text matching and local edits win."""
import argparse
import gzip
import hashlib
import io
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app_config import RESOURCE_DIR, data_dir
from extractor import atomic_json, read_json
from saved_translations import valid_unit

SCHEMA = 1
MAX_FILE = 32 * 1024 * 1024
_lock = threading.RLock()


def library_key(mod):
    # Workshop IDs are portable. Local IDs contain a machine-specific path hash,
    # so prefer the game's authored namespace for local mods.
    ident = str(mod.get('id', ''))
    stable = 'workshop:' + ident if ident.isdecimal() else 'namespace:' + str(mod.get('namespace') or ident)
    return hashlib.sha256(stable.encode()).hexdigest()


def cache_root():
    return data_dir() / 'shared-library-cache'


def load_index():
    candidates = []
    for root in (RESOURCE_DIR / 'shared-library', cache_root()):
        try:
            value = json.loads((root / 'index.json').read_text(encoding='utf-8'))
            if (value.get('schema') == SCHEMA and isinstance(value.get('mods'), dict)
                    and isinstance(value.get('titles'), dict) and isinstance(value.get('updated_at', ''), str)):
                candidates.append(value)
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return max(candidates, key=lambda item: item.get('updated_at', '')) if candidates else {'schema': SCHEMA, 'mods': {}, 'titles': {}}


def sync_index():
    from github_client import repository_file
    value = json.loads(repository_file('shared-library/index.json', limit=4 * 1024 * 1024))
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or not isinstance(value.get('mods'), dict) or not isinstance(value.get('titles'), dict):
        raise ValueError('Unsupported shared translation index.')
    with _lock:
        atomic_json(cache_root() / 'index.json', value)
    return value


def sync_mod(mod, index=None):
    from github_client import repository_file
    index = load_index() if index is None else index
    key = library_key(mod)
    entry = index.get('mods', {}).get(key)
    if not entry:
        return False
    path = cache_root() / (key + '.json.gz')
    expected = entry.get('sha256')
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError('Invalid shared translation checksum.')
    with _lock:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            return True
        payload = repository_file('shared-library/' + key + '.json.gz', limit=MAX_FILE)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError('Shared translation checksum did not match.')
        decode(payload)
        from installer import atomic_bytes
        atomic_bytes(path, payload)
    return True


def decode(payload):
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError('Shared translation file is too large after decompression.')
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or not isinstance(value.get('translations'), dict):
        raise ValueError('Unsupported shared translation format.')
    return value


def apply_shared(project, target='en'):
    if target != 'en':
        return 0
    key = library_key(project.get('mod', {}))
    entry = load_index().get('mods', {}).get(key, {})
    for root in (cache_root(), RESOURCE_DIR / 'shared-library'):
        try:
            payload = (root / (key + '.json.gz')).read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry.get('sha256'):
                continue
            shared = decode(payload)
            if shared.get('key') != key or shared.get('target') != target:
                continue
            values = shared['translations']
            count = 0
            for unit in project.get('units', []):
                if unit.get('translation') or unit.get('retranslation_pending') or unit.get('category') == 'technical':
                    continue
                candidate = {**unit, 'translation': values.get(unit['source']), 'status': 'shared'}
                if valid_unit(candidate):
                    unit.update(translation=candidate['translation'], status='shared')
                    count += 1
            return count
        except (OSError, ValueError, EOFError, TypeError, AttributeError):
            continue
    return 0


def reuse_titles(mods, titles, index=None):
    from mod_titles import record, saved_title, validate_title
    index = load_index() if index is None else index
    count = 0
    for mod in mods:
        if saved_title(titles, mod):
            continue
        item = index.get('titles', {}).get(library_key(mod), {})
        if item.get('source') == mod.get('name') and not validate_title(mod['name'], item.get('title')):
            record(titles, mod, item['title'])
            count += 1
    return count


def export_library(project_root, output, titles=None):
    """Publisher-only export: no paths, credentials, game binaries or user metadata."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    try:
        index = json.loads((output / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        index = {'schema': SCHEMA, 'mods': {}, 'titles': {}}
    from mod_titles import saved_title, validate_title
    for path in sorted(Path(project_root).glob('*/project.json')):
        project = read_json(path)
        mod = project.get('mod', {})
        if path.parent.name != str(mod.get('id', '')):
            continue  # Diagnostic/export copies must not overwrite the mod's main project.
        key = library_key(mod)
        translations = {u['source']: u['translation'] for u in project.get('units', [])
                        if u.get('category') != 'technical' and valid_unit(u)}
        if translations:
            value = {'schema': SCHEMA, 'key': key, 'target': 'en', 'translations': translations}
            payload = gzip.compress(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(), mtime=0)
            (output / (key + '.json.gz')).write_bytes(payload)
            index['mods'][key] = {'sha256': hashlib.sha256(payload).hexdigest(), 'entries': len(translations), 'bytes': len(payload)}
        title = saved_title(titles or {}, mod)
        if title and not validate_title(mod['name'], title):
            index['titles'][key] = {'source': mod['name'], 'title': title}
    # Title-only mods can be shared even before their contents are translated.
    for ident, item in (titles or {}).items():
        if str(ident).isdecimal() and not validate_title(item['source'], item['title']):
            index['titles'][library_key({'id': ident})] = item
    index['updated_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(output / 'index.json', index)
    return {'mods': len(index['mods']), 'entries': sum(m['entries'] for m in index['mods'].values()),
            'bytes': sum(m['bytes'] for m in index['mods'].values()), 'titles': len(index['titles'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export reviewed saved translations for sharing through GitHub.')
    parser.add_argument('--projects', type=Path, default=data_dir() / 'projects')
    parser.add_argument('--output', type=Path, default=RESOURCE_DIR / 'shared-library')
    args = parser.parse_args()
    from mod_titles import load_titles
    print(json.dumps(export_library(args.projects, args.output, load_titles()), indent=2))
