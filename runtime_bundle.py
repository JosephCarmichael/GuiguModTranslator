"""Ship only our compiled runtime, verifying that it matches the checked-in sources."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREBUILT = ROOT / 'loader' / 'prebuilt'


def source_digest():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'loader').glob('*.cs')):
        digest.update(path.name.encode())
        digest.update(path.read_text(encoding='utf-8-sig').encode())
    return digest.hexdigest()


def save_runtime():
    runtime = ROOT / 'runtime'
    manifest = json.loads((runtime / 'manifest.json').read_text(encoding='utf-8-sig'))
    payload = (runtime / 'GuiguModTranslation.dll').read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest['sha256']:
        raise ValueError('Runtime checksum mismatch. Rebuild the loader first.')
    manifest['source_sha256'] = source_digest()
    PREBUILT.mkdir(parents=True, exist_ok=True)
    (PREBUILT / 'GuiguModTranslation.dll').write_bytes(payload)
    (PREBUILT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def restore_runtime():
    manifest = json.loads((PREBUILT / 'manifest.json').read_text(encoding='utf-8'))
    payload = (PREBUILT / 'GuiguModTranslation.dll').read_bytes()
    if manifest['source_sha256'] != source_digest() or hashlib.sha256(payload).hexdigest() != manifest['sha256']:
        raise ValueError('The loader sources changed. Build and test locally, then run runtime_bundle.py before publishing.')
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    shutil.copy2(PREBUILT / 'GuiguModTranslation.dll', runtime / 'GuiguModTranslation.dll')
    shutil.copy2(PREBUILT / 'manifest.json', runtime / 'manifest.json')


if __name__ == '__main__':
    save_runtime()
