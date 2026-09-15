"""Reproduce the bundled proxy's path check without launching the game."""
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
source = r'''
#include <windows.h>
#include <stdio.h>
int main() {
 DWORD h = 0;
 printf("BEFORE proxy; ACP=%u\n", GetACP());
 GetFileVersionInfoSizeW(L"nonexistent-file", &h);
 puts("AFTER proxy");
 return 42;
}
'''
with tempfile.TemporaryDirectory(prefix='GuiguProxyPath-') as directory:
    temp = Path(directory)
    cs = temp/'Probe.c'; cs.write_text(source)
    exe = temp/'Probe.exe'
    vcvars = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'
    build = temp/'build.cmd'
    build.write_text('@echo off\ncall "'+vcvars+'" >nul\ncl /nologo /MT /Fe:"'+str(exe)+'" "'+str(cs)+'" /link version.lib\n')
    subprocess.run(['cmd.exe','/d','/c',str(build)], cwd=temp, check=True)
    with zipfile.ZipFile(root/'bootstrap/MelonLoader.x64.zip') as z: proxy = z.read('version.dll')
    results = []
    for name in ('ASCII', '\u9b3c\u8c37\u516b\u8352'):
        folder = temp/name; folder.mkdir()
        (folder/'Probe.exe').write_bytes(exe.read_bytes())
        (folder/'version.dll').write_bytes(proxy)
        data = folder/'Probe_Data'; data.mkdir(); (data/'globalgamemanagers').write_bytes(b'fixture')
        result = subprocess.run([str(folder/'Probe.exe'), '--no-mods'], cwd=folder, capture_output=True, text=True, timeout=15)
        results.append({'folder':name, 'exit_code':result.returncode, 'output':result.stdout.strip(), 'stderr':result.stderr.strip()})
    print(json.dumps(results,ensure_ascii=False,indent=2))
    (root/'evidence/proxy-path-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
