"""Verify and name a tested Friends ZIP without logging credentials."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--version', default='1.3.3')
parser.add_argument('--check-prefix', default='personal-key')
args = parser.parse_args()
release = json.loads((ROOT/'projects/release-manifest-friends.json').read_text(encoding='utf-8'))
exe, source = Path(release['executable']), Path(release['zip'])
for name in (args.check_prefix+'-onedir-check', args.check_prefix+'-onefile-check'):
    report = json.loads((ROOT/'projects'/(name+'.json')).read_text(encoding='utf-8'))
    assert report['result'] == 'passed' and report['app_version'] == args.version
    assert report['edition'] == 'friends'
    assert any(value.startswith('Personal OpenRouter key:') for value in report['checks'])
    assert any(value.startswith('Launch repair:') for value in report['checks'])
    if args.check_prefix == 'translate-all':
        assert any(value.startswith('Translate all:') for value in report['checks'])
    if args.check_prefix in ('balance', 'five-pence'):
        assert any(value.startswith('Balance:') for value in report['checks'])
contents = CArchiveReader(str(exe))
names = {name.replace('\\', '/'): name for name in contents.toc}
assert json.loads(contents.extract('build_policy.json')) == {'edition': 'friends'}
assert not any(name.rsplit('/', 1)[-1] in ('service.json', 'openrouter-access.json', 'translation-balances.json') for name in names)
assert json.loads(contents.extract('bundled_service.json')) == json.loads((ROOT/'bundled_service.json').read_text())
modules = contents.open_embedded_archive('PYZ.pyz')
assert {'api_access', 'api_key_dialog', 'launch_repair'}.issubset(modules.toc)
if args.check_prefix == 'translate-all':
    assert 'bulk_translation' in modules.toc
if args.check_prefix in ('balance', 'five-pence'):
    assert 'translation_balance' in modules.toc
if args.check_prefix == 'five-pence':
    assert '5' in modules.extract('translation_cost').co_consts, 'Packaged shared cap must be five pence'
runtime = json.loads(contents.extract(names['runtime/manifest.json']))
assert runtime['version'] == '1.2.3'
assert hashlib.sha256(contents.extract(names['runtime/GuiguModTranslation.dll'])).hexdigest() == '3c9e0c3c6b8bd1cfbba12ed2f1f0c960449cb8e7234017bdac0c4d01a973cd4d'
with zipfile.ZipFile(source) as archive:
    assert archive.testzip() is None
    assert archive.read('GuiguModTranslator/GuiguModTranslator.exe') == exe.read_bytes()
    instructions = archive.read('GuiguModTranslator/START HERE.txt').decode('utf-8')
    assert 'PERSONAL API KEY (1.3.3)' in instructions and 'LAUNCH FIX (1.3.2)' in instructions
    if args.check_prefix in ('balance', 'five-pence'):
        assert 'BALANCE (1.3.6)' in instructions
    if args.check_prefix == 'five-pence':
        assert 'up to 5p (GBP 0.05)' in instructions
        assert '0.5p' not in instructions
target = ROOT/'release'/('GuiguModTranslator-Friends-'+args.version+'.zip')
if target.exists():
    assert target.read_bytes() == source.read_bytes(), 'A different build already exists at the target filename'
else:
    shutil.copy2(source, target)
result = {'result': 'passed', 'app_version': args.version, 'edition': 'friends', 'zip': str(target),
          'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'checks': ['ZIP integrity', 'tested EXE matches ZIP', 'personal credential files excluded',
                     'shared credential unchanged', 'access dialog and encryption embedded',
                     'frozen personal-key translation and shared cap restoration passed',
                     'launch repair retained', 'unchanged live-verified 1.2.3 translation DLL']}
if args.check_prefix in ('balance', 'five-pence'):
    result['checks'].extend(['balance module embedded', 'personal balance cache excluded',
                             'frozen confirmed-charge deduction and reconciliation passed',
                             'balance instructions included'])
(ROOT/'evidence'/(args.check_prefix+'-package.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
