"""Edition-aware GitHub updates, checksum validation, and a rollback-safe Windows handoff."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from app_config import APP_VERSION, data_dir, build_edition
from github_client import API_ROOT, read_bytes, read_json, open_request

MAX_DOWNLOAD = 300 * 1024 * 1024
MAX_EXTRACTED = 500 * 1024 * 1024
MANIFEST = 'update-manifest.json'


def version_tuple(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(version))
    if not match:
        raise ValueError('Unsupported update version.')
    return tuple(map(int, match.groups()))


def edition():
    return build_edition()


def asset_url(asset):
    ident = asset.get('id')
    if type(ident) is not int or ident <= 0:
        raise ValueError('Invalid release asset.')
    return API_ROOT + '/releases/assets/' + str(ident)


def check_update(current=APP_VERSION, build_edition=None):
    release = read_json(API_ROOT + '/releases/latest')
    if release.get('draft') or release.get('prerelease'):
        return None
    version = release.get('tag_name', '')
    if version_tuple(version) <= version_tuple(current):
        return None
    assets = {item['name']: item for item in release.get('assets', [])}
    if MANIFEST not in assets:
        raise ValueError('This release has no verified update package yet.')
    manifest = json.loads(read_bytes(asset_url(assets[MANIFEST]), binary=True, limit=128 * 1024))
    if manifest.get('schema') != 1 or version_tuple(manifest.get('version')) != version_tuple(version):
        raise ValueError('The release and update manifest versions do not match.')
    build_edition = build_edition or edition()
    package = manifest.get('editions', {}).get(build_edition)
    if not isinstance(package, dict) or package.get('asset') not in assets:
        raise ValueError('This release does not include your edition.')
    for field in ('sha256', 'exe_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', str(package.get(field, ''))):
            raise ValueError('The update package is missing a checksum.')
    return {'version': str(manifest['version']), 'edition': build_edition,
            'asset': assets[package['asset']], 'sha256': package['sha256'],
            'exe_sha256': package['exe_sha256'], 'notes': str(release.get('body') or '')[:4000]}


def prepare_update(update, progress=None, stop=None):
    progress = progress or (lambda message: None)
    stop = stop or (lambda: False)
    stage = data_dir() / 'updates' / uuid.uuid4().hex
    stage.mkdir(parents=True)
    archive = stage / 'download.zip'
    digest = hashlib.sha256()
    total = 0
    try:
        with open_request(asset_url(update['asset']), binary=True) as response, archive.open('wb') as out:
            while True:
                if stop():
                    raise InterruptedError('Update cancelled.')
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError('Update download is too large.')
                out.write(chunk)
                digest.update(chunk)
                progress(f'Downloading update… {total / 1024 / 1024:.1f} MB')
        if digest.hexdigest() != update['sha256']:
            raise ValueError('Update checksum did not match. Your current app has not been changed.')
        with zipfile.ZipFile(archive) as package:
            files = package.infolist()
            if sum(item.file_size for item in files) > MAX_EXTRACTED:
                raise ValueError('Update archive is too large.')
            names = set()
            for item in files:
                path = PurePosixPath(item.filename.replace('\\', '/'))
                if path.is_absolute() or '..' in path.parts or ':' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe update archive path.')
                if str(path) in names:
                    raise ValueError('Duplicate update archive entry.')
                names.add(str(path))
            name = 'GuiguModTranslator/GuiguModTranslator.exe'
            if name not in names:
                raise ValueError('The update archive does not contain the app.')
            executable = stage / 'GuiguModTranslator.exe'
            with package.open(name) as source, executable.open('wb') as out:
                shutil.copyfileobj(source, out)
        if hashlib.sha256(executable.read_bytes()).hexdigest() != update['exe_sha256']:
            raise ValueError('The executable checksum did not match.')
        archive.unlink()
        return {**update, 'executable': str(executable)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def launch_installer(prepared):
    if not getattr(sys, 'frozen', False) or os.name != 'nt':
        raise ValueError('Automatic installation is available in the Windows EXE. Update a source checkout with Git.')
    from extractor import atomic_json
    executable = Path(prepared['executable'])
    plan = {'schema': 1, 'parent_pid': os.getpid(), 'target': sys.executable,
            'source': str(executable), 'sha256': prepared['exe_sha256'], 'data': str(data_dir())}
    path = executable.parent / 'install.json'
    atomic_json(path, plan)
    subprocess.Popen([str(executable), '--apply-update', str(path)], cwd=executable.parent,
                     creationflags=subprocess.CREATE_NO_WINDOW)


def wait_for_parent(pid, timeout=120):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return  # The original process has already exited.
        raise OSError('Could not wait for the current app to close.')
    try:
        if kernel.WaitForSingleObject(handle, timeout * 1000) != 0:
            raise TimeoutError('The current app did not close. Reopen it and retry the update.')
    finally:
        kernel.CloseHandle(handle)


def apply_update(plan_path):
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    source, target = Path(plan['source']).resolve(), Path(plan['target']).resolve()
    if plan.get('schema') != 1 or source.parent != plan_path.parent or source == target:
        raise ValueError('Invalid update installation plan.')
    if hashlib.sha256(source.read_bytes()).hexdigest() != plan['sha256']:
        raise ValueError('The staged update has changed.')
    wait_for_parent(int(plan['parent_pid']))
    backup = target.with_suffix('.previous.exe')
    temporary = target.with_suffix('.update.exe')
    old_moved = False
    try:
        shutil.copy2(source, temporary)
        # A one-file app has a bootloader process as well as the Python process.
        # Windows may hold its executable briefly after the Python process exits.
        deadline = time.monotonic() + 20
        while True:
            try:
                os.replace(target, backup)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.25)
        old_moved = True
        os.replace(temporary, target)
        env = dict(os.environ, GUIGU_TRANSLATOR_DATA=plan['data'])
        subprocess.Popen([str(target)], cwd=target.parent, env=env)
    except Exception:
        if old_moved:
            os.replace(backup, target)
        temporary.unlink(missing_ok=True)
        raise
    from extractor import atomic_json
    atomic_json(Path(plan['data']) / 'update-last.json', {'state': 'installed', 'sha256': plan['sha256']})


def write_release_manifest(packages, output):
    manifest = {'schema': 1, 'version': APP_VERSION, 'editions': {}}
    for build_edition, filename in packages.items():
        archive = Path(filename)
        with zipfile.ZipFile(archive) as package:
            executable = package.read('GuiguModTranslator/GuiguModTranslator.exe')
        manifest['editions'][build_edition] = {'asset': archive.name,
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'exe_sha256': hashlib.sha256(executable).hexdigest()}
    Path(output).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
