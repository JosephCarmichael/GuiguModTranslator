"""Install reversible display translations for the game's bundled MelonLoader."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app_config import RESOURCE_DIR
from extractor import validate_translation

LOADER = 'GuiguModTranslation.dll'
FORMAT = 'guigu-installed-v1'


def paths(game):
    game = Path(game).resolve()
    return game / 'Mods' / LOADER, game / 'UserData' / 'GuiguModTranslator' / 'installed.json'


def preflight(game, runtime_dir=None):
    game = Path(game).resolve()
    required = ['guigubahuang.exe', 'version.dll', 'MelonLoader/MelonLoader.dll',
                'MelonLoader/0Harmony.dll', 'MelonLoader/Managed/UnhollowerBaseLib.dll',
                'MelonLoader/Managed/Assembly-CSharp.dll',
                'MelonLoader/Managed/UnityEngine.UI.dll', 'MelonLoader/Managed/Unity.TextMeshPro.dll']
    if any(not (game / p).is_file() for p in required):
        raise ValueError('Choose a Tale of Immortal installation with its bundled MelonLoader 0.5.x. '
                         'Launch the game once to generate its managed assemblies.')
    data = runtime_payload(runtime_dir)
    # These are build ABI requirements, not hashes of proprietary game files.
    if melon_version(game)[:2] != (0, 5):
        raise ValueError('This loader targets the game’s bundled MelonLoader 0.5.x; this installation uses another version.')
    return data


def runtime_payload(runtime_dir=None):
    """Validate our own DLL before first-launch game assemblies exist."""
    runtime = Path(runtime_dir) if runtime_dir else RESOURCE_DIR / 'runtime'
    source = runtime / LOADER
    if not source.is_file() or not (runtime / 'manifest.json').is_file():
        raise ValueError('The translation loader is missing. Rebuild the app or use the updated release.')
    data = source.read_bytes()
    manifest = json.loads((runtime / 'manifest.json').read_text(encoding='utf-8'))
    if not data.startswith(b'MZ') or hashlib.sha256(data).hexdigest() != manifest['sha256']:
        raise ValueError('The bundled translation loader failed its integrity check.')
    return data


def melon_version(game):
    import dnfile
    assembly = dnfile.dnPE(str(Path(game) / 'MelonLoader/MelonLoader.dll'))
    try:
        row = assembly.net.mdtables.Assembly.rows[0]
        return row.MajorVersion, row.MinorVersion, row.BuildNumber
    finally:
        assembly.close()


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(store):
    store.parent.mkdir(parents=True, exist_ok=True)
    lock = store.with_suffix('.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('Another installation is in progress. If an earlier app crashed, close it and remove ' + str(lock))
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def read_store(store):
    if not store.exists():
        return {'format': FORMAT, 'mods': {}}
    value = json.loads(store.read_text(encoding='utf-8'))
    if value.get('format') != FORMAT or not isinstance(value.get('mods'), dict):
        raise ValueError('Unknown installed translation format; existing installation was kept.')
    return value


def commit_store(store, value):
    data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    if store.exists():
        backup = store.parent / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex + '.json')
        atomic_bytes(backup, store.read_bytes())
    atomic_bytes(store, data)
    if json.loads(store.read_text(encoding='utf-8')) != value:
        raise OSError('Installation verification failed.')


def install(project, game, runtime_dir=None):
    payload = preflight(game, runtime_dir)
    mod = project['mod']
    if not Path(mod['path']).exists():
        raise ValueError('The source mod has moved or was removed. Refresh mods and extract it again.')
    entries = {}
    skipped = 0
    conflicts = set()
    # Prefer explicit edits, then existing mod translations, then machine output.
    # Stable IDs and text break ties without depending on extraction order.
    rank = {'edited': 0, 'existing': 1}
    units = sorted(project['units'], key=lambda u: (rank.get(u.get('status'), 2),
                   str(u.get('id', '')), u.get('translation') or ''))
    for unit in units:
        source, target = unit['source'], unit.get('translation', '')
        if unit['category'] == 'technical':
            continue
        if not target or not target.strip() or unit.get('status') == 'needs_review' or validate_translation(source, target):
            skipped += 1
            continue
        if source in entries and entries[source] != target:
            conflicts.add(source)
        entries.setdefault(source, target)
    if not entries:
        raise ValueError('No validated translations are ready to install. Saved work has been kept.')
    loader, store = paths(game)
    with locked(store):
        value = read_store(store)
        for ident, other in value['mods'].items():
            if ident == mod['id']:
                continue
            for source, target in entries.items():
                previous = other['entries'].get(source)
                if previous is not None and previous != target:
                    conflicts.add(source)
        # Keep each mod's dictionary intact. The runtime chooses the newest
        # installation; uninstalling it naturally reveals the previous wording.
        order = max((other.get('install_order', 0) for other in value['mods'].values()), default=0) + 1
        value['mods'][mod['id']] = {'name': mod['name'], 'source_path': str(Path(mod['path']).resolve()),
                                   'installed_at': datetime.now(timezone.utc).isoformat(), 'install_order': order,
                                   'conflicts_resolved': len(conflicts), 'entries': entries}
        old_loader = loader.read_bytes() if loader.exists() else None
        changed = old_loader != payload
        wrote_loader = False
        try:
            if changed:
                if old_loader:
                    atomic_bytes(store.parent / 'backups' / (uuid.uuid4().hex + '.dll'), old_loader)
                atomic_bytes(loader, payload)
                wrote_loader = True
            commit_store(store, value)
        except Exception:
            if wrote_loader:
                if old_loader is None:
                    loader.unlink(missing_ok=True)
                else:
                    atomic_bytes(loader, old_loader)
            raise
    return {'state': 'installed', 'count': len(entries), 'skipped': skipped, 'mod': mod['id'],
            'conflicts_resolved': len(conflicts), 'restart_required': True, 'store': str(store), 'loader': str(loader)}


def install_detector(game, runtime_dir=None):
    """Install the capture-capable loader even before any translations exist."""
    payload = preflight(game, runtime_dir)
    loader, store = paths(game)
    with locked(store):
        previous = loader.read_bytes() if loader.exists() else None
        if previous == payload:
            return False
        if previous:
            atomic_bytes(store.parent / 'backups' / (uuid.uuid4().hex + '.dll'), previous)
        atomic_bytes(loader, payload)
    return True


def installation_message(result, partial=False):
    message = f'Installed {result["count"]:,} translations.'
    if result.get('conflicts_resolved'):
        message += f' Automatically resolved {result["conflicts_resolved"]:,} text conflicts.'
    if partial:
        message += ' Some text still needs review.'
    return message + ' Restart the game to use them.'


def uninstall(mod_id, game):
    _, store = paths(game)
    with locked(store):
        value = read_store(store)
        removed = value['mods'].pop(mod_id, None)
        if removed:
            commit_store(store, value)
    return {'state': 'removed' if removed else 'not_installed', 'mod': mod_id, 'restart_required': True}


def installation_status(game):
    loader, store = paths(game)
    value = read_store(store)
    return {'loader_present': loader.is_file(), 'mods': {key: {'name': mod['name'], 'count': len(mod['entries'])}
            for key, mod in value['mods'].items()}, 'store': str(store)}
