"""Verify the latest Friends executable without sending paid requests."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT/'projects/release-manifest-friends.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(prefix='Friends cost portable ') as folder:
    temp = Path(folder)
    exe = temp/'GuiguModTranslator.exe'
    shutil.copy2(manifest['executable'], exe)
    saved = temp/'project.json'
    project = {'mod': {'id': 'expensive'}, 'coverage': {'files': []},
               'units': [{'id': 'one', 'source': '宝剑' * 5000, 'translation': '',
                          'category': 'player_text', 'status': 'untranslated', 'occurrences': []}]}
    saved.write_text(json.dumps(project), encoding='utf-8')
    original = saved.read_bytes()
    env = dict(os.environ, GUIGU_TRANSLATOR_DATA=str(temp/'data'),
               PATH=str(Path(os.environ['SystemRoot'])/'System32'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    result = subprocess.run([str(exe), 'translate', str(temp)], cwd=temp, env=env, timeout=60)
    error = (temp/'data/last-error.log').read_text(encoding='utf-8')
    assert result.returncode == 1 and '0.5p' in error and saved.read_bytes() == original
    subprocess.run([str(exe), '--game', str(ROOT.parent), 'scan-destinies', '--output', str(temp/'destinies')],
                   cwd=temp, env=env, timeout=120, check=True)
    destiny = json.loads((temp/'destinies/project.json').read_text(encoding='utf-8'))
    assert destiny['mod']['id'] == 'character-creation-destinies' and len(destiny['units']) > 0
    report = {'result': 'passed', 'edition': 'friends', 'package_sha256': manifest['sha256'],
              'checkpoint_unchanged': True, 'destiny_texts': len(destiny['units']),
              'checks': ['copied executable with no Python in PATH', 'CLI full-mod limit before requests',
                         'saved project unchanged', 'real destiny scan available in friends edition']}
    (ROOT/'evidence/cost-friends-cli-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8', newline='\n')
    print('Friends CLI limit and real destiny scan passed')
