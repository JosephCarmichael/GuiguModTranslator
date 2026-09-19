"""Read-only launch diagnostics, saved as text and copied to the Windows clipboard."""
from __future__ import annotations
import base64
import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from app_config import APP_DIR, APP_VERSION, data_dir, installed_game
from installer import atomic_bytes

REPORT_NAME = 'Guigu-Logs.txt'
LOG_LIMIT = 128 * 1024
GAME_FILES = (
    'guigubahuang.exe', 'version.dll', 'MelonLoader/MelonLoader.dll', 'MelonLoader/0Harmony.dll',
    'MelonLoader/Dependencies/Bootstrap.dll',
    'MelonLoader/Dependencies/MonoBleedingEdge.x64/mono-2.0-bdwgc.dll',
    'MelonLoader/Dependencies/SupportModules/Il2Cpp.dll',
    'MelonLoader/Dependencies/Il2CppAssemblyGenerator/Il2CppAssemblyGenerator.dll',
    'MelonLoader/Managed/Assembly-CSharp.dll', 'MelonLoader/Managed/UnhollowerBaseLib.dll',
    'Mods/GuiguModTranslation.dll',
)


def redact(text):
    text = re.sub(r'\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{12,}', '[REDACTED GITHUB TOKEN]', text)
    text = re.sub(r'\bsk-(?:or-)?[A-Za-z0-9_-]{12,}', '[REDACTED KEY]', text)
    text = re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*', r'\1[REDACTED]', text)
    text = re.sub(r'''(?i)((?:["']?)(?:api[_-]?key|access[_-]?token|authorization)(?:["']?)\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,&}\r\n]+)''',
                  r'\1[REDACTED]', text)
    return text


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def log_text(path, limit=LOG_LIMIT):
    """Retain original times and mark truncation; tolerate locked/missing logs."""
    try:
        info = path.stat()
        with path.open('rb') as stream:
            stream.seek(max(0, info.st_size - limit))
            data = stream.read(limit)
        header = f'Source: {path}\nModified UTC: {datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()}\nBytes: {info.st_size}\n'
        if info.st_size > limit:
            header += f'[Showing last {limit:,} bytes]\n'
        return header + '\n' + data.decode('utf-8-sig', errors='replace')
    except FileNotFoundError:
        return 'Not present: ' + str(path)
    except OSError as exc:
        return f'Could not read {path}: {exc}'


def file_info(path):
    result = {'file': str(path)}
    try:
        info = path.stat()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        result.update(present=True, bytes=info.st_size,
                      modified_utc=datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(), sha256=digest.hexdigest())
    except FileNotFoundError:
        result['present'] = False
    except OSError as exc:
        result['error'] = str(exc)
    return result


def steam_root():
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                return Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        except OSError:
            return Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam'
    return None


def system_info(game):
    result = {'collected_utc': datetime.now(timezone.utc).isoformat(), 'app_version': APP_VERSION,
              'windows': platform.platform(), 'machine': platform.machine(), 'game': str(game) if game else None,
              'game_path_contains_non_ascii': bool(game and not str(game).isascii())}
    if os.name == 'nt':
        codepage = ctypes.windll.kernel32.GetACP()
        result['windows_ansi_code_page'] = codepage
        try:
            str(game or '').encode('cp' + str(codepage))
            result['game_path_unrepresentable_in_ansi'] = False
        except (UnicodeEncodeError, LookupError):
            result['game_path_unrepresentable_in_ansi'] = True
        from windows_prerequisites import missing_runtimes
        try:
            result['missing_microsoft_runtimes'] = missing_runtimes()
        except Exception as exc:
            result['runtime_check_error'] = str(exc)
        if game:
            from game_setup import game_processes
            try:
                result['running_game_pids'] = sorted(game_processes(game))
            except Exception as exc:
                result['process_check_error'] = str(exc)
    return result


def windows_events():
    if os.name != 'nt':
        return 'Windows application events are available on Windows only.'
    script = r'''
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
 $events = @(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001,1026,33,59;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 2000 -ErrorAction Stop |
  Where-Object {$_.Message -match 'guigubahuang|TaleOfImmortal|Tale of Immortal|MelonLoader|GuiguModTranslator|Cpp2IL|AssemblyUnhollower'} |
  Select-Object -First 30 TimeCreated,Id,ProviderName,Message)
 if ($events.Count) { ConvertTo-Json -InputObject $events -Depth 4 } else { 'No matching application crash events found in the last 7 days.' }
} catch { 'Windows crash events unavailable: ' + $_.Exception.Message }
'''
    command = [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
               '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(script.encode('utf-16le')).decode()]
    try:
        result = subprocess.run(command, capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout.decode('utf-8-sig', errors='replace')
        if result.returncode:
            output += '\nEvent query failed: ' + result.stderr.decode('utf-8', errors='replace')
        if len(output) > LOG_LIMIT:
            output = output[:LOG_LIMIT] + '\n[Windows event output truncated]'
        return output
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'Could not read Windows crash events: ' + str(exc)


def build_report(game=None, live_status=None, app_data=None, player_dir=None):
    game = Path(game) if game else installed_game()
    app_data = Path(app_data) if app_data else data_dir()
    player = Path(player_dir) if player_dir else Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'AppData/LocalLow/guigugame/guigubahuang'
    sections = ['GUIGU MOD TRANSLATOR — LAUNCH LOGS\nCopy this report or send Guigu-Logs.txt.']
    def section(title, value):
        sections.append('\n===== ' + title + ' =====\n' + value)
    section('System and current app state', json_text({'system': system_info(game), 'live_app_state': live_status or {}}))
    for name in ('setup-last.json', 'last-error.log', 'launch-repair-pending.json'):
        section('Translator ' + name, log_text(app_data / name))
    if game:
        section('Game file checks', json_text([file_info(game / name) for name in GAME_FILES]))
        for name in ('MelonLoader/Latest.log', 'UserData/GuiguModTranslator/runtime-status.json',
                     'UserData/GuiguModTranslator/setup-pending.json', 'UserData/GuiguModTranslator/setup-complete.json',
                     'MelonLoader/Dependencies/Il2CppAssemblyGenerator/Config.cfg'):
            section(name, log_text(game / name))
        try:
            histories = sorted((game / 'MelonLoader/Logs').glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for path in histories:
                section('Loader history ' + path.name, log_text(path))
        except OSError as exc:
            section('Loader history', str(exc))
    for name in ('Player.log', 'Player-prev.log'):
        section(name, log_text(player / name))
    section('Windows application crashes', windows_events())
    steam = steam_root()
    if steam:
        for name in ('gameprocess_log.txt', 'console_log.txt'):
            tail = log_text(steam / 'logs' / name, limit=512 * 1024)
            lines = tail.splitlines()
            relevant = [line for line in lines[4:] if re.search(r'1468810|guigubahuang|TaleOfImmortal|MelonLoader', line, re.I)]
            section('Steam ' + name, '\n'.join(lines[:4]) + '\n' + ('\n'.join(relevant[-250:]) or 'No matching launch lines.'))
    return redact('\n'.join(sections).replace('\r\n', '\n').replace('\r', '\n'))


def copy_to_clipboard(text, window_handle):
    """CF_UNICODETEXT ownership goes to Windows, so text survives app exit."""
    if os.name != 'nt':
        raise OSError('Windows clipboard is unavailable.')
    from ctypes import wintypes as w
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [w.HWND]; user.OpenClipboard.restype = w.BOOL
    user.EmptyClipboard.restype = w.BOOL
    user.SetClipboardData.argtypes = [w.UINT, w.HANDLE]; user.SetClipboardData.restype = w.HANDLE
    user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p]
    user.CreateWindowExW.restype = w.HWND
    user.DestroyWindow.argtypes = [w.HWND]
    kernel.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]; kernel.GlobalAlloc.restype = w.HGLOBAL
    kernel.GlobalLock.argtypes = [w.HGLOBAL]; kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [w.HGLOBAL]
    kernel.GlobalFree.argtypes = [w.HGLOBAL]; kernel.GlobalFree.restype = w.HGLOBAL
    encoded = text.replace('\x00', '').encode('utf-16-le') + b'\x00\x00'
    memory = kernel.GlobalAlloc(0x0002, len(encoded))
    if not memory:
        raise OSError('Could not allocate clipboard text.')
    opened = False
    owner = None
    try:
        pointer = kernel.GlobalLock(memory)
        if not pointer:
            raise OSError('Could not prepare clipboard text.')
        ctypes.memmove(pointer, encoded, len(encoded)); kernel.GlobalUnlock(memory)
        # Tk clears clipboard ownership during window teardown. A temporary
        # native STATIC window avoids Tk's delayed-rendering clipboard handler.
        owner = user.CreateWindowExW(0, 'STATIC', 'Guigu log clipboard', 0, 0, 0, 0, 0,
                                     w.HWND(-3), None, None, None)
        if not owner:
            raise OSError('Could not open a clipboard window.')
        for _ in range(20):
            if user.OpenClipboard(owner):
                opened = True; break
            time.sleep(.05)
        if not opened:
            raise OSError('Another app is using the clipboard.')
        if not user.EmptyClipboard() or not user.SetClipboardData(13, memory):
            raise OSError('Windows could not copy the logs.')
        memory = None  # Windows now owns the memory.
    finally:
        if opened:
            user.CloseClipboard()
        if owner:
            user.DestroyWindow(owner)
        if memory:
            kernel.GlobalFree(memory)


def collect_logs(game=None, live_status=None, window_handle=0, output_dir=None):
    report = build_report(game, live_status)
    result = {'text': report, 'path': None, 'copied': False, 'errors': []}
    path = (Path(output_dir) if output_dir else APP_DIR) / REPORT_NAME
    try:
        atomic_bytes(path, report.encode('utf-8-sig'))
        result['path'] = str(path)
    except OSError as exc:
        result['errors'].append('Saving the report: ' + str(exc))
    try:
        copy_to_clipboard(report, window_handle)
        result['copied'] = True
    except OSError as exc:
        result['errors'].append('Copying the report: ' + str(exc))
    return result
