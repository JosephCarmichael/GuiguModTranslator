"""Real Windows proxy before/after repair; never start or edit the real game."""
import ctypes
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import launch_repair

SOURCE = r'''
#include <windows.h>
#include <stdio.h>
int main() {
    DWORD handle = 0;
    printf("MAIN reached; ACP=%u\n", GetACP());
    GetFileVersionInfoSizeW(L"nonexistent-file", &handle);
    puts("VERSION proxy forwarded successfully");
    return 42;
}
'''

with tempfile.TemporaryDirectory(prefix='GuiguLaunchRepair-') as directory:
    temp = Path(directory)
    source = temp / 'probe.c'
    source.write_text(SOURCE)
    exe = temp / 'guigubahuang.exe'
    vcvars = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'
    build = temp / 'build.cmd'
    build.write_text('@echo off\ncall "' + vcvars + '" >nul\ncl /nologo /MT /Fe:"' + str(exe) +
                     '" "' + str(source) + '" /link version.lib\n')
    subprocess.run(['cmd.exe', '/d', '/c', str(build)], cwd=temp, check=True)
    game = temp / 'steamapps/common/鬼谷八荒'
    game.mkdir(parents=True)
    (game / exe.name).write_bytes(exe.read_bytes())
    with zipfile.ZipFile(ROOT / 'bootstrap/MelonLoader.x64.zip') as archive:
        proxy = archive.read('version.dll')
    (game / 'version.dll').write_bytes(proxy)
    data = game / 'guigubahuang_Data'
    data.mkdir()
    (data / 'globalgamemanagers').write_bytes(b'fixture')
    manifest = temp / 'steamapps/appmanifest_1468810.acf'
    manifest.write_text('"AppState" { "appid" "1468810" "installdir" "鬼谷八荒" }', encoding='utf-8')
    appdata = temp / 'appdata'
    appdata.mkdir()

    def launch_from_manifest():
        name = re.search(r'"installdir"\s*"([^"]+)"', manifest.read_text(encoding='utf-8'))[1]
        folder = temp / 'steamapps/common' / name
        result = subprocess.run([str(folder / exe.name), '--no-mods'], cwd=folder,
                                capture_output=True, text=True, timeout=15)
        return {'path': str(folder), 'exit_code': result.returncode, 'stdout': result.stdout.strip()}

    before = launch_from_manifest()
    assert ctypes.windll.kernel32.GetACP() == 1252, 'This regression requires the friend’s ACP 1252'
    assert before['exit_code'] == 0 and not before['stdout'], before
    # Steam itself is kept running and unmodified. Only the fixture's process
    # guard is mocked; the rename, manifest edit and Windows junction are real.
    with patch('launch_repair.data_dir', return_value=appdata), \
         patch('app_config.data_dir', return_value=appdata), \
         patch('launch_repair.short_game_path', return_value=None), \
         patch('launch_repair.steam_running', return_value=False):
        target = launch_repair.repair_game_path(game, lambda *_: None, lambda: False)
    after = launch_from_manifest()
    assert after['exit_code'] == 42 and 'forwarded successfully' in after['stdout'], after
    assert (target / exe.name).read_bytes() == exe.read_bytes()
    assert (game / 'version.dll').read_bytes() == proxy
    result = {'result': 'passed', 'windows_ansi_code_page': 1252,
              'proxy_sha256': hashlib.sha256(proxy).hexdigest(), 'before': before, 'after': after,
              'checks': ['exact bundled proxy', 'original failure reproduced', 'real directory rename',
                         'real Windows junction', 'manifest-derived launch reaches main after repair',
                         'unchanged executable and proxy', 'old-path references preserved'],
              'limits': 'A native harness was launched with --no-mods; the real game and Steam state were not changed.'}
    (ROOT / 'evidence/launch-repair-native.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
