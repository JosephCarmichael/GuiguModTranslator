"""Publish both verified editions and their checksums as a GitHub release."""
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
    packages = {edition: ROOT / 'release' / ('GuiguModTranslator-' + edition.title() + '.zip')
                for edition in ('friends', 'personal')}
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
    notes = ('Mod artwork, automatic persistent English titles, verified completion ticks,\n'
             'retranslation with backups, shared translations and in-app GitHub updates.\n\n'
             'Download Friends for shared access with the 5p cap, or Personal for your own unrestricted edition.\n'
             'Existing saved translations and API settings are preserved.\n')
    with tempfile.TemporaryDirectory(prefix='Guigu release ') as folder:
        body = Path(folder) / 'notes.md'
        body.write_text(notes, encoding='utf-8')
        subprocess.run(['gh', 'release', 'create', tag, '--repo', REPOSITORY, '--target', 'main',
                        '--title', 'Guigu Mod Translator ' + APP_VERSION, '--notes-file', str(body),
                        str(packages['friends']), str(packages['personal']), str(manifest)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    publish(args.publish)
