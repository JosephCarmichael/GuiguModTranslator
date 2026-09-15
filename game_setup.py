"""Automatic, reversible setup using pinned, bundled upstream releases.

Game binaries and generated game assemblies are never distributed. MelonLoader
creates the latter locally on the owner's first game launch.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from app_config import RESOURCE_DIR, data_dir
from installer import atomic_bytes, melon_version, paths, preflight, runtime_payload

ASSETS = RESOURCE_DIR / 'bootstrap'
GENERATOR = 'MelonLoader/Dependencies/Il2CppAssemblyGenerator/'
CACHES = {
    'Cpp2IL.zip': GENERATOR + 'Cpp2IL_2022.1.0-pre-release.3.zip',
    'Unhollower.zip': GENERATOR + 'Il2CppAssemblyUnhollower_0.4.18.0.zip',
    'UnityDependencies.zip': GENERATOR + 'UnityDependencies_2020.3.9.zip',
}
TOOL_DIRS = {'Cpp2IL.zip': 'Cpp2IL', 'Unhollower.zip': 'Il2CppAssemblyUnhollower',
             'UnityDependencies.zip': 'UnityDependencies'}
MANAGED = ('UnhollowerBaseLib.dll', 'Assembly-CSharp.dll', 'UnityEngine.UI.dll', 'Unity.TextMeshPro.dll')


def cancelled(stop):
    if stop():
        raise InterruptedError('Setup stopped. Open the app again to continue.')


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def safe_name(name):
    parts = name.split('/')
    if (not name or '\\' in name or PurePosixPath(name).is_absolute()
            or any(p in ('', '.', '..') or p.endswith((' ', '.'))
                   or re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts)):
        raise ValueError('The bundled setup archive contains an unsafe path.')
    return name


def verify_assets(asset_dir=None):
    assets = Path(asset_dir) if asset_dir else ASSETS
    manifest = read_json(assets / 'manifest.json')
    if manifest.get('melonloader_version') != '0.5.4' or set(manifest.get('assets', {})) != {'MelonLoader.x64.zip', *CACHES}:
        raise ValueError('Setup files are incomplete. Download the friends ZIP again.')
    for name, info in manifest['assets'].items():
        p = assets / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('A bundled setup file failed its integrity check. Download the friends ZIP again.')
    with zipfile.ZipFile(assets / 'MelonLoader.x64.zip') as archive:
        seen = set()
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = safe_name(item.filename)
            if (name != 'version.dll' and name != 'NOTICE.txt' and not name.startswith('MelonLoader/')) or name.casefold() in seen:
                raise ValueError('Unexpected file in the bundled loader.')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Links are not allowed in setup archives.')
            seen.add(name.casefold())
        if archive.testzip():
            raise ValueError('The bundled loader archive is damaged.')
    return manifest


def validate_game(game):
    game = Path(game).resolve()
    for name in ('guigubahuang.exe', 'GameAssembly.dll', 'guigubahuang_Data/il2cpp_data/Metadata/global-metadata.dat'):
        if not (game / name).is_file():
            raise ValueError('Tale of Immortal is not fully installed. Finish its Steam download, then click Retry setup.')
    import pefile
    pe = pefile.PE(str(game / 'guigubahuang.exe'), fast_load=True)
    try:
        if pe.FILE_HEADER.Machine != 0x8664:
            raise ValueError('This app needs the 64-bit Windows edition of Tale of Immortal.')
    finally:
        pe.close()
    return game


def game_processes(game):
    """Match the executable path, including Steam libraries and junctions."""
    if os.name != 'nt':
        return set()
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', w.DWORD),
                    ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD),
                    ('pcPriClassBase', w.LONG), ('dwFlags', w.DWORD), ('szExeFile', w.WCHAR * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    k.OpenProcess.argtypes, k.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    k.CloseHandle.argtypes = [w.HANDLE]
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError('Windows could not check whether the game is running. Please try again.')
    result = set()
    entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
    expected = Path(game).resolve() / 'guigubahuang.exe'
    try:
        ok = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == 'guigubahuang.exe':
                process = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not process:
                    # Cannot safely edit files when a game process is inaccessible.
                    raise PermissionError('Windows needs permission to check the running game.')
                try:
                    buffer = ctypes.create_unicode_buffer(32768); length = w.DWORD(len(buffer))
                    if not k.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
                        raise PermissionError('Windows could not check the running game folder.')
                    if Path(buffer.value).resolve() == expected:
                        result.add(entry.th32ProcessID)
                finally:
                    k.CloseHandle(process)
            ok = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return result


@contextmanager
def setup_lock(game):
    # OS locks release on process exit, including a crash. No stale lock cleanup.
    path = data_dir() / ('setup-' + hashlib.sha256(str(game).casefold().encode()).hexdigest()[:20] + '.lock')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another translator is setting up this game. Wait for it to finish, then retry.')
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def destination(game, name):
    path = game / safe_name(name)
    if not path.resolve().is_relative_to(game):
        raise ValueError('A setup folder points outside the game. Existing files were kept.')
    # Reject even internal reparse points: do not modify another installation.
    for parent in [path, *path.parents]:
        if parent == game:
            break
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('A setup folder is linked to another location. Existing files were kept.')
    return path


def setup_plan(game, asset_dir=None):
    """Never replace a working third-party loader or unrelated mods."""
    game = validate_game(game)
    assets = Path(asset_dir) if asset_dir else ASSETS
    verify_assets(assets)
    core = game / 'MelonLoader/MelonLoader.dll'
    if core.exists():
        if melon_version(game)[:2] != (0, 5):
            raise ValueError('This game uses a different MelonLoader version. Setup kept it and your mods unchanged. '
                             'This translator supports MelonLoader 0.5.x; send the setup report for help.')
    elif (game / 'version.dll').exists():
        raise ValueError('Another launcher is already installed in this game. Setup kept it unchanged. Send the setup report for help.')
    pending = {}
    # Leave a complete, compatible installation alone, including its optional
    # compatibility plugins. Steam's bundled build need not equal our archive.
    try:
        preflight(game)
        complete = all((game / n).is_file() for n in (
            'MelonLoader/Dependencies/Bootstrap.dll',
            'MelonLoader/Dependencies/SupportModules/Il2Cpp.dll',
            'MelonLoader/Dependencies/MonoBleedingEdge.x64/mono-2.0-bdwgc.dll'))
    except ValueError:
        complete = False
    with zipfile.ZipFile(assets / 'MelonLoader.x64.zip') as archive:
        for item in archive.infolist():
            if item.is_dir() or item.filename == 'NOTICE.txt':
                continue
            target = destination(game, item.filename)
            if not target.exists() and not complete:
                pending[item.filename] = archive.read(item)
            elif target.exists() and not target.is_file():
                raise ValueError('A folder is blocking a required setup file: ' + item.filename)
    needs_generation = any(not (game / 'MelonLoader/Managed' / n).is_file() for n in MANAGED)
    if needs_generation:
        # Only the matching Unity reference package is bundled. Other versions
        # use MelonLoader's own download during startup, with clear progress.
        for source, target in CACHES.items():
            destination(game, target)
            data = (assets / source).read_bytes()
            if not (game / target).is_file() or (game / target).read_bytes() != data:
                pending[target] = data
            # Repair absent tools even when an existing generator cache claims
            # that its versions are up to date.
            with zipfile.ZipFile(assets / source) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    name = GENERATOR + TOOL_DIRS[source] + '/' + safe_name(item.filename)
                    destination(game, name)
                    if stat.S_ISLNK(item.external_attr >> 16):
                        raise ValueError('Links are not allowed in setup archives.')
                    payload = archive.read(item)
                    if not (game / name).is_file() or (game / name).read_bytes() != payload:
                        pending[name] = payload
    loader = 'Mods/GuiguModTranslation.dll'
    target = destination(game, loader)
    payload = runtime_payload()
    if not target.is_file() or target.read_bytes() != payload:
        pending[loader] = payload
    return pending, needs_generation


def install_files(game, pending, progress, stop):
    """Back up replacements, rollback on failure/cancel, leave dictionaries alone."""
    changed = []
    backup = game / 'UserData/GuiguModTranslator/backups' / ('setup-' + uuid.uuid4().hex)
    total = sum(map(len, pending.values())) or 1
    done = 0
    try:
        for name, payload in pending.items():
            cancelled(stop)
            if game_processes(game):
                raise ValueError('The game started during setup. Close it and click Retry setup.')
            target = destination(game, name)
            previous = target.read_bytes() if target.exists() else None
            if previous is not None:
                atomic_bytes(backup / name, previous)
            atomic_bytes(target, payload)
            changed.append((target, previous))
            if target.read_bytes() != payload:
                raise OSError('Could not verify a setup file: ' + name)
            done += len(payload)
            progress(10 + 35 * done / total, 'Installing MelonLoader and the translation plugin…')
        cancelled(stop)
    except Exception:
        for target, previous in reversed(changed):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                atomic_bytes(target, previous)
        raise


def launch_game(game, first_setup=False):
    """Use Steam so ownership checks and Workshop subscriptions behave normally."""
    if os.name != 'nt':
        raise ValueError('Automatic game setup runs on Windows 10/11.')
    if game_processes(game):
        return
    import winreg
    steam = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0]) / 'steam.exe'
    except OSError:
        pass
    if not steam or not steam.is_file():
        candidate = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam/steam.exe'
        if candidate.is_file():
            steam = candidate
    args = []
    if first_setup:
        args = ['--melonloader.agfregenerate', '--melonloader.agfvdumper', '2022.1.0-pre-release.3',
                '--melonloader.agfvunhollower', '0.4.18.0']
        managers = Path(game) / 'guigubahuang_Data/globalgamemanagers'
        if managers.is_file() and b'2020.3.9' in managers.read_bytes()[:256]:
            args.append('--melonloader.agfoffline')
    if steam and steam.is_file():
        subprocess.Popen([str(steam), '-applaunch', '1468810', *args], cwd=str(game))
    else:
        subprocess.Popen([str(Path(game) / 'guigubahuang.exe'), *args], cwd=str(game))


def wait_for_runtime(game, started, progress, stop, timeout=1200):
    status_path = game / 'UserData/GuiguModTranslator/runtime-status.json'
    runtime_version = read_json(RESOURCE_DIR / 'runtime/manifest.json')['version']
    deadline = time.monotonic() + timeout
    seen_game = False
    absent_since = None
    stage = 50
    while time.monotonic() < deadline:
        cancelled(stop)
        pids = game_processes(game)
        seen_game |= bool(pids)
        now = time.monotonic()
        if not pids:
            absent_since = absent_since or now
            if (seen_game and now - absent_since > 15) or (not seen_game and now - absent_since > 120):
                raise ValueError('The game exited or could not start. Click Collect logs and send Guigu-Logs.txt '
                                 'so the startup failure can be checked. Setup details were saved with the app.')
        else:
            absent_since = None
        status = read_json(status_path)
        if (status.get('process_id') in pids and status.get('version') == runtime_version
                and status_path.stat().st_mtime >= started):
            errors = status.get('errors') or []
            if errors:
                raise ValueError('The translator reported a startup problem: ' + str(errors[0]))
            if status.get('hooks'):
                preflight(game)
                return {'process_id': status['process_id'], 'runtime_version': runtime_version}
        log = game / 'MelonLoader/Latest.log'
        message = 'Starting Tale of Immortal through Steam…'
        if log.exists() and log.stat().st_mtime >= started:
            # Read only the tail, since startup logs can be large.
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 64000))
                tail = stream.read().decode('utf-8', errors='replace')
            if 'Assembly Generation Failed' in tail or 'Failed to Execute' in tail or 'Failed to Download' in tail:
                raise ValueError('The game could not finish its first-time setup. Check your internet connection and click Retry setup.')
            if 'Cpp2IL' in tail:
                stage, message = max(stage, 60), 'Preparing the game for mods. The first launch can take several minutes…'
            if 'Executing Il2CppAssemblyUnhollower' in tail or '[Il2CppAssemblyUnhollower]' in tail:
                stage, message = max(stage, 75), 'Building the game’s mod interfaces…'
            if 'Assembly Generation Successful' in tail or 'No Generation Needed' in tail or 'Loading Mods' in tail:
                stage, message = max(stage, 90), 'Loading the game and checking the translator…'
        if stage >= 90:
            message = 'Loading the game and checking the translator…'
        progress(stage, message)
        time.sleep(1)
    raise TimeoutError('First-time game setup is taking longer than expected. Click Retry setup to continue checking. '
                       'Your game has been left running.')


def ensure_setup(game, progress=lambda *_: None, stop=lambda: False):
    game = Path(game).resolve()
    report = {'game': str(game), 'state': 'checking', 'started': time.time()}
    def update(percent, message):
        progress(percent, message)
        report.update(progress=round(percent), message=message)
    try:
        with setup_lock(game):
            update(2, 'Checking your Tale of Immortal installation…')
            validate_game(game)
            from launch_repair import repair_game_path
            original_game = game
            game = repair_game_path(game, update, stop)
            report['game'] = str(game)
            if game != original_game:
                report['launch_path_repaired'] = True
            pending, generation = setup_plan(game)
            cancelled(stop)
            marker = game / 'UserData/GuiguModTranslator/setup-complete.json'
            # Existing working installations require no game launch. If a first
            # launch was interrupted, retry the live check instead of claiming success.
            awaiting = read_json(game / 'UserData/GuiguModTranslator/setup-pending.json')
            if not pending and not generation and not awaiting:
                preflight(game)
                update(100, 'Game setup is ready.')
                report['state'] = 'ready'
                return report
            while pending and game_processes(game):
                update(5, 'Save and close Tale of Immortal. Setup will continue automatically…')
                cancelled(stop)
                time.sleep(1)
            from windows_prerequisites import ensure_prerequisites
            ensure_prerequisites(update, stop)
            if pending:
                install_files(game, pending, update, stop)
            pending_path = destination(game, 'UserData/GuiguModTranslator/setup-pending.json')
            atomic_bytes(pending_path, json.dumps({'started': time.time()}).encode())
            cancelled(stop)
            update(50, 'Starting Tale of Immortal for its first-time setup…')
            started = time.time() - 1
            launch_game(game, first_setup=generation)
            report['runtime'] = wait_for_runtime(game, started, update, stop)
            atomic_bytes(marker, json.dumps(report['runtime']).encode())
            pending_path.unlink(missing_ok=True)
            update(100, 'Setup complete — the translator is running in your game.')
            report['state'] = 'ready'
            return report
    except Exception as exc:
        report.update(state='cancelled' if isinstance(exc, InterruptedError) else 'error', error=str(exc))
        raise
    finally:
        atomic_bytes(data_dir() / 'setup-last.json', json.dumps(report, indent=2).encode())


def restart_elevated(game):
    """One Windows permission prompt when the Steam folder is protected."""
    if os.name != 'nt':
        raise PermissionError('Automatic setup needs Windows permission to write into the game folder.')
    args = ['--setup-game', str(game)]
    if not getattr(sys, 'frozen', False):
        args.insert(0, str(RESOURCE_DIR / 'entry.py'))
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    if shell.IsUserAnAdmin():
        raise PermissionError('Windows is still blocking this game folder. Close the game and retry setup; '
                              'if it continues, send setup-last.json from the app data folder.')
    shell.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                   ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    result = shell.ShellExecuteW(None, 'runas', sys.executable, subprocess.list2cmdline(args), str(RESOURCE_DIR), 1)
    if not result or result <= 32:
        raise PermissionError('Windows permission was not granted. Click Retry setup to try again.')
