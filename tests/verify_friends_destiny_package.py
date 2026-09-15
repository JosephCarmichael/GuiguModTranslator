"""Verify the friends ZIP ships the exact destiny loader confirmed in the game."""
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[1]
archive = root / 'release/GuiguModTranslator-Friends.zip'
expected = hashlib.sha256((root.parent / 'Mods/GuiguModTranslation.dll').read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as package, tempfile.TemporaryDirectory() as temporary:
    assert package.testzip() is None
    assert set(package.namelist()) == {'GuiguModTranslator/' + name for name in (
        'GuiguModTranslator.exe', 'Launch.bat', 'START HERE.txt', 'THIRD PARTY LICENSES.txt', 'THIRD PARTY SOURCES.zip')}
    executable = Path(temporary) / 'GuiguModTranslator.exe'
    executable.write_bytes(package.read('GuiguModTranslator/GuiguModTranslator.exe'))
    contents = CArchiveReader(str(executable))
    names = {name.replace('\\', '/'): name for name in contents.toc}
    manifest = json.loads(contents.extract(names['runtime/manifest.json']))
    policy = json.loads(contents.extract(names['build_policy.json']))
    payload = contents.extract(names['runtime/GuiguModTranslation.dll'])
    actual = hashlib.sha256(payload).hexdigest()
    assert manifest['version'] == '1.2.3'
    assert actual == manifest['sha256'] == expected
    assert policy == {'edition': 'friends'}
    setup = json.loads(contents.extract(names['bootstrap/manifest.json']))
    assert setup['melonloader_version'] == '0.5.4'
    for asset, info in setup['assets'].items():
        assert hashlib.sha256(contents.extract(names['bootstrap/' + asset])).hexdigest() == info['sha256']
    assert package.read('GuiguModTranslator/THIRD PARTY SOURCES.zip') == (root/'third_party/THIRD PARTY SOURCES.zip').read_bytes()
    instructions = package.read('GuiguModTranslator/START HERE.txt').decode()
    assert 'Watch the setup bar' in instructions and 'Start the game once first' not in instructions
    report = {'result': 'passed', 'version': manifest['version'], 'edition': policy['edition'],
              'zip': str(archive), 'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'embedded_loader_sha256': actual, 'matches_live_confirmed_loader': True,
              'setup_version': setup['melonloader_version'],
              'checks': ['ZIP integrity', 'friends edition', 'exact working loader', 'package contents',
                         'bundled loader and first-launch tools', 'corresponding upstream source', 'automatic setup instructions']}
    (root / 'evidence/friends-destiny-1.2.3-package.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (root / 'evidence/friends-autosetup-package.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
