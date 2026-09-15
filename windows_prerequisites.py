"""Install missing Microsoft runtimes from Microsoft, after signature validation."""
import base64
import ctypes
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

RUNTIMES = {
    'Visual C++': 'https://aka.ms/vs/17/release/vc_redist.x64.exe',
    '.NET Framework': 'https://go.microsoft.com/fwlink/?LinkId=2085155',
}


def missing_runtimes():
    if os.name != 'nt':
        return []
    import winreg
    missing = []
    system = Path(os.environ['SystemRoot']) / 'System32'
    if any(not (system / n).is_file() for n in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')):
        missing.append('Visual C++')
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as key:
            release = winreg.QueryValueEx(key, 'Release')[0]
    except OSError:
        release = 0
    if release < 461808:  # .NET Framework 4.7.2, used by the bundled Cpp2IL.
        missing.append('.NET Framework')
    return missing


def verify_microsoft_signature(path):
    # The downloaded path is passed as data, never interpolated into PowerShell.
    script = "$s=Get-AuthenticodeSignature -LiteralPath $env:GUIGU_PREREQUISITE; " \
             "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch '(?:^|, )O=Microsoft Corporation(?:,|$)') { exit 1 }"
    env = dict(os.environ, GUIGU_PREREQUISITE=str(path))
    result = subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                             '-NoProfile', '-NonInteractive', '-EncodedCommand',
                             base64.b64encode(script.encode('utf-16le')).decode()],
                            env=env, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError('Microsoft runtime verification failed. Check your connection and retry setup.')


def ensure_prerequisites(progress, stop):
    missing = missing_runtimes()
    if not missing:
        return
    # The GUI automatically reopens with the ordinary Windows permission prompt.
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('Windows needs permission to install a missing game runtime.')
    for title in missing:
        with tempfile.TemporaryDirectory(prefix='GuiguRuntime-') as folder:
            target = Path(folder) / 'MicrosoftRuntime.exe'
            progress(6, 'Downloading the required Microsoft ' + title + ' runtime…')
            request = urllib.request.Request(RUNTIMES[title], headers={'User-Agent': 'GuiguModTranslator/1.3'})
            with urllib.request.urlopen(request, timeout=45) as response, target.open('wb') as output:
                total = int(response.headers.get('Content-Length', 0)); done = 0
                while True:
                    if stop():
                        raise InterruptedError('Setup stopped. Open the app again to continue.')
                    block = response.read(256 * 1024)
                    if not block:
                        break
                    output.write(block); done += len(block)
                    progress(6 + min(2, 2 * done / total) if total else 6,
                             'Downloading Microsoft ' + title + f'… {done // 1024:,} KB')
            verify_microsoft_signature(target)
            progress(9, 'Installing Microsoft ' + title + '…')
            process = subprocess.Popen([str(target), '/install', '/quiet', '/norestart'] if title == 'Visual C++'
                                       else [str(target), '/q', '/norestart'])
            while process.poll() is None:
                # Let Windows finish an installation already started, even if
                # the app is cancelled. Killing an MSI can damage system state.
                if stop():
                    progress(9, 'Finishing the Windows runtime installation before stopping…')
                time.sleep(.5)
            if process.returncode in (3010, 1641):
                raise ValueError('Windows installed the required runtime. Restart your PC, then open this app to finish setup.')
            if process.returncode != 0:
                raise ValueError('Windows could not install ' + title + '. Click Retry setup. Code: ' + str(process.returncode))
            if stop():
                raise InterruptedError('Setup stopped. The required Windows runtime is installed.')
    if missing_runtimes():
        raise ValueError('Restart Windows, then reopen this app to finish installing the game runtimes.')
