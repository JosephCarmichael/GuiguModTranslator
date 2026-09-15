"""Name and verify the final Friends launch-fix archive without logging keys."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT/'projects/release-manifest-friends.json').read_text(encoding='utf-8'))
source, exe = Path(manifest['zip']), Path(manifest['executable'])
for name in ('launch-fix-onedir-check', 'launch-fix-onefile-check'):
    check = json.loads((ROOT/'projects'/(name+'.json')).read_text(encoding='utf-8'))
    assert check['result'] == 'passed' and check['app_version'] == '1.3.2' and check['edition'] == 'friends'
    assert any(value.startswith('Launch repair:') for value in check['checks'])
contents = CArchiveReader(str(exe))
names = {name.replace('\\', '/'): name for name in contents.toc}
assert json.loads(contents.extract('build_policy.json')) == {'edition': 'friends'}
runtime = json.loads(contents.extract(names['runtime/manifest.json']))
assert runtime['version'] == '1.2.3'
assert hashlib.sha256(contents.extract(names['runtime/GuiguModTranslation.dll'])).hexdigest() == runtime['sha256']
modules = contents.open_embedded_archive('PYZ.pyz')
assert 'launch_repair' in modules.toc
with zipfile.ZipFile(source) as archive:
    assert archive.testzip() is None
    assert archive.read('GuiguModTranslator/GuiguModTranslator.exe') == exe.read_bytes()
    instructions = archive.read('GuiguModTranslator/START HERE.txt').decode('utf-8')
    assert 'LAUNCH FIX (1.3.2)' in instructions and 'Steam > Exit' in instructions
target = ROOT/'release/GuiguModTranslator-Friends-LaunchFix-1.3.2.zip'
if target.exists():
    assert target.read_bytes() == source.read_bytes(), 'A different build already exists at the target filename'
else:
    shutil.copy2(source, target)
result = {'result': 'passed', 'app_version': '1.3.2', 'edition': 'friends',
          'zip': str(target), 'bytes': target.stat().st_size,
          'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'runtime_version': runtime['version'], 'runtime_sha256': runtime['sha256'],
          'checks': ['ZIP integrity', 'tested executable matches ZIP', 'Friends policy',
                     'repair module embedded', 'offline portable repair checks passed in both bundle formats',
                     'unchanged translation runtime', 'launch-fix instructions included']}
(ROOT/'evidence/launch-repair-package.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
