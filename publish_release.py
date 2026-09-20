"""Publish the credential-free public package and their checksums as a GitHub release."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from app_config import APP_VERSION
from app_updates import write_release_manifest
from github_client import REPOSITORY

ROOT = Path(__file__).resolve().parent


def publish(publish_now=False):
    archive = ROOT / 'release' / 'GuiguModTranslator-Public.zip'
    # Existing Friends/Personal installations migrate to the same key-free app.
    packages = {edition: archive for edition in ('public', 'friends', 'personal')}
    import tempfile
    import zipfile
    from PyInstaller.archive.readers import CArchiveReader
    from release_security import verify_archive
    with tempfile.TemporaryDirectory() as folder:
        executable = Path(folder) / 'GuiguModTranslator.exe'
        with zipfile.ZipFile(archive) as package:
            executable.write_bytes(package.read('GuiguModTranslator/GuiguModTranslator.exe'))
        verify_archive(CArchiveReader(str(executable)))
    manifest = ROOT / 'release' / 'update-manifest.json'
    write_release_manifest(packages, manifest)
    tag = 'v' + APP_VERSION
    if not publish_now:
        print('Prepared ' + str(manifest))
        return
    # Versioned releases are immutable to users of the updater. A later push
    # must bump APP_VERSION; it must never silently replace an existing version.
    existing = subprocess.run(['gh', 'release', 'view', tag, '--repo', REPOSITORY], capture_output=True)
    if existing.returncode == 0:
        print(tag + ' is already published. Bump APP_VERSION for the next update.')
        return
    notes = ('Download GuiguModTranslator-Public.zip for Windows 10/11 (64-bit).\n\n'
             'No API keys are included. Google Translate is available without a key as an experimental web option.\n'
             'OpenRouter Free and Paid use your own key. Saved translations and settings are preserved.\n'
             'Google may throttle requests; OpenRouter Free has account-wide daily quotas.\n'
             'Existing Friends/Personal apps can install this release through the updater.\n')
    with tempfile.TemporaryDirectory(prefix='Guigu release ') as folder:
        body = Path(folder) / 'notes.md'
        body.write_text(notes, encoding='utf-8')
        subprocess.run(['gh', 'release', 'create', tag, '--repo', REPOSITORY, '--target', 'main',
                        '--title', 'Guigu Mod Translator ' + APP_VERSION, '--notes-file', str(body),
                        str(archive), str(manifest)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    publish(args.publish)
