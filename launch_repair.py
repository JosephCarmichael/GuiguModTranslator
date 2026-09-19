"""Repair MelonLoader 0.5's ANSI-path startup failure without changing binaries.

Rename the Steam installation on the same volume, retain an old-path junction
for saved mod references, and update only installdir in its Steam manifest.
Steam must be closed. A journal allows an interrupted repair to finish on retry.
"""
from __future__ import annotations

import csv
import ctypes
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app_config import data_dir, save_preferences
from installer import atomic_bytes


def unsupported_path(game):
    if os.name != 'nt':
        return False
    codepage = ctypes.windll.kernel32.GetACP()
    try:
        str(game).encode('cp' + str(codepage))
        return False
    except (UnicodeEncodeError, LookupError):
        return True


def short_game_path(game):
    """Use the existing Windows 8.3 name when Steam can launch it as ASCII."""
    if os.name != 'nt':
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(game), buffer, len(buffer))
    if not size or size >= len(buffer):
        return None
    target = Path(game).parent / Path(buffer.value).name
    if unsupported_path(target) or target.resolve() != Path(game).resolve():
        return None
    return target


def steam_running():
    if os.name != 'nt':
        return False
    result = subprocess.run(
        [str(Path(os.environ['SystemRoot']) / 'System32/tasklist.exe'),
         '/FI', 'IMAGENAME eq steam.exe', '/FO', 'CSV', '/NH'],
        capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return any(row and row[0].casefold() == 'steam.exe'
               for row in csv.reader(io.StringIO(result.stdout.decode('utf-8', errors='replace'))))


def make_junction(target, link):
    import _winapi
    _winapi.CreateJunction(str(target), str(link))


def is_junction(path):
    return path.is_junction() if os.name == 'nt' else path.is_symlink()


def replace_install_dir(raw, game_name, target_name):
    text = raw.decode('utf-8-sig')
    ids = re.findall(r'"appid"\s*"([^"]+)"', text)
    dirs = list(re.finditer(r'("installdir"\s*")([^"\r\n]+)(")', text))
    if ids != ['1468810'] or len(dirs) != 1 or dirs[0][2] != game_name:
        raise ValueError('Steam’s installation record does not match this game folder. Click Collect logs for help.')
    match = dirs[0]
    text = text[:match.start(2)] + target_name + text[match.end(2):]
    return (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')


def wait_until_closed(game, progress, stop):
    from game_setup import cancelled, game_processes
    while True:
        cancelled(stop)
        if game_processes(game):
            progress(3, 'Save and close Tale of Immortal so its launch folder can be repaired…')
        elif steam_running():
            progress(3, 'To fix game launch, choose Steam > Exit (closing its window is not enough). '
                     'Setup will repair the launch path and restart Steam automatically.')
        else:
            return
        time.sleep(1)


def _finish(plan, journal, progress, stop):
    source, target = Path(plan['source']), Path(plan['target'])
    manifest, backup = Path(plan['manifest']), Path(plan['backup'])
    before = backup.read_bytes()
    if hashlib.sha256(before).hexdigest() != plan['before_sha256']:
        raise ValueError('The launch-repair backup failed its integrity check. Click Collect logs for help.')
    after = replace_install_dir(before, plan.get('manifest_source_name', source.name), target.name)
    if plan.get('strategy') == 'short_path':
        if (source.parent != target.parent or unsupported_path(target)
                or target.resolve() != source.resolve()
                or source.stat().st_ino != plan['directory_id']):
            raise ValueError('The saved short launch path no longer identifies this game installation.')
        # The Steam manifest may already be correct. No restart is needed then.
        if manifest.read_bytes() != after:
            wait_until_closed(source, progress, stop)
            if manifest.read_bytes() not in (before, after):
                raise ValueError('Steam’s installation record changed during repair. Exit Steam and retry setup.')
            progress(6, 'Repairing Steam’s launch path without moving game files…')
            if steam_running():
                raise ValueError('Steam reopened during launch repair. Exit Steam, then click Retry setup.')
            atomic_bytes(manifest, after)
            if manifest.read_bytes() != after:
                raise OSError('Could not verify Steam’s repaired installation record.')
        save_preferences(game=str(target))
        from game_setup import destination
        atomic_bytes(destination(source, 'UserData/GuiguModTranslator/setup-pending.json'),
                     json.dumps({'started': time.time(), 'reason': 'short launch path repaired'}).encode())
        plan['state'] = 'complete'
        atomic_bytes(backup.parent / 'repair.json', json.dumps(plan, indent=2).encode('utf-8'))
        journal.unlink(missing_ok=True)
        return target
    # Refuse to overwrite edits made by Steam or a person after our backup.
    if manifest.read_bytes() not in (before, after):
        raise ValueError('Steam’s installation record changed during launch repair. Exit Steam and click Collect logs for help.')
    if source.parent != target.parent or source == target or unsupported_path(target):
        raise ValueError('The saved launch-repair folder is invalid. Click Collect logs for help.')
    if target.exists():
        if (not (target / 'guigubahuang.exe').is_file() or is_junction(target)
                or target.stat().st_ino != plan['directory_id']):
            raise ValueError('The launch-repair destination is not the expected game folder.')
        if source.exists() and (not is_junction(source) or source.resolve() != target.resolve()):
            raise ValueError('Both launch-repair folders exist. Existing files were kept; click Collect logs for help.')
    elif not source.is_dir() or is_junction(source) or source.stat().st_ino != plan['directory_id']:
        raise ValueError('The original game folder is missing. Click Collect logs for help.')
    wait_until_closed(target if target.exists() else source, progress, stop)
    # Check again after the user closes Steam, which can flush its manifest.
    if manifest.read_bytes() not in (before, after):
        raise ValueError('Steam updated its installation record. Click Retry setup after Steam has exited.')
    progress(6, 'Repairing the game’s launch folder…')
    try:
        if not target.exists():
            source.rename(target)
        if not source.exists():
            make_junction(target, source)
        if steam_running():
            raise ValueError('Steam reopened during launch repair. Exit Steam, then click Retry setup.')
        if manifest.read_bytes() not in (before, after):
            raise ValueError('Steam’s installation record changed during repair. Click Collect logs for help.')
        atomic_bytes(manifest, after)
        if manifest.read_bytes() != after:
            raise OSError('Could not verify Steam’s repaired installation record.')
    except Exception:
        # Roll back only our manifest content, never an unrelated Steam update.
        current = manifest.read_bytes()
        if current in (before, after):
            if current == after:
                atomic_bytes(manifest, before)
            if source.exists() and is_junction(source) and source.resolve() == target.resolve():
                source.rmdir() if os.name == 'nt' else source.unlink()
            if target.exists() and not source.exists():
                target.rename(source)
            journal.unlink(missing_ok=True)
        raise
    # After the filesystem transaction succeeds, retain the pending journal if
    # saving preferences fails: the next run can complete without moving again.
    save_preferences(game=str(target))
    from game_setup import destination
    atomic_bytes(destination(target, 'UserData/GuiguModTranslator/setup-pending.json'),
                 json.dumps({'started': time.time(), 'reason': 'launch path repaired'}).encode())
    plan['state'] = 'complete'
    atomic_bytes(backup.parent / 'repair.json', json.dumps(plan, indent=2).encode('utf-8'))
    journal.unlink(missing_ok=True)
    return target


def repair_game_path(game, progress, stop):
    game = Path(game).resolve()
    journal = data_dir() / 'launch-repair-pending.json'
    if journal.exists():
        plan = json.loads(journal.read_text(encoding='utf-8'))
        if game not in (Path(plan['source']).resolve(), Path(plan['target']).resolve()):
            raise ValueError('Another game-folder repair is unfinished. Choose that installation and retry setup.')
        return _finish(plan, journal, progress, stop)
    if not unsupported_path(game):
        return game
    short_path = short_game_path(game)
    # The portable EXE/data cannot be inside the directory it is moving.
    if not short_path and (Path(sys.executable).resolve().is_relative_to(game) or data_dir().resolve().is_relative_to(game)):
        raise ValueError('The game’s Chinese folder name prevents MelonLoader from starting. '
                         'Extract the updated translator into Downloads, outside the game folder, then open it to repair launch.')
    if game.parent.name.casefold() != 'common' or game.parent.parent.name.casefold() != 'steamapps':
        raise ValueError('The game folder cannot be read by MelonLoader with your Windows character settings. '
                         'Choose its installed Steam library folder so setup can repair it.')
    target = short_path or game.with_name('TaleOfImmortal')
    index = 2
    while not short_path and target.exists():
        target = game.with_name('TaleOfImmortal-' + str(index))
        index += 1
    if unsupported_path(target):
        raise ValueError('The Steam library path also contains characters MelonLoader cannot read. '
                         'Use Steam > Settings > Storage to move the game to an English-named library, then retry setup.')
    manifest = game.parent.parent / 'appmanifest_1468810.acf'
    if not manifest.is_file():
        raise ValueError('Steam’s Tale of Immortal installation record is missing. Click Collect logs for help.')
    before = manifest.read_bytes()
    names = re.findall(r'"installdir"\s*"([^"\r\n]+)"', before.decode('utf-8-sig'))
    if (len(names) != 1 or Path(names[0]).name != names[0]
            or (game.parent / names[0]).resolve() != game):
        raise ValueError('Steam’s installation record does not match this game folder. Click Collect logs for help.')
    manifest_source_name = names[0]
    replace_install_dir(before, manifest_source_name, target.name)
    if short_path and manifest_source_name == target.name:
        return target
    wait_until_closed(game, progress, stop)
    if manifest.read_bytes() != before:
        raise ValueError('Steam’s installation record changed. Click Retry setup after Steam has exited.')
    backup = data_dir() / 'launch-repairs' / uuid.uuid4().hex / manifest.name
    atomic_bytes(backup, before)
    plan = {'state': 'pending', 'source': str(game), 'target': str(target),
            'manifest_source_name': manifest_source_name,
            'strategy': 'short_path' if short_path else 'rename',
            'manifest': str(manifest), 'backup': str(backup),
            'directory_id': game.stat().st_ino,
            'before_sha256': hashlib.sha256(before).hexdigest()}
    atomic_bytes(journal, json.dumps(plan, indent=2).encode('utf-8'))
    return _finish(plan, journal, progress, stop)
