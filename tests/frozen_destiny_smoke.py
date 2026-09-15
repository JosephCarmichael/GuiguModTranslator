"""Run the packaged destiny scan from an isolated folder without source Python."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='Guigu Destiny Portable ') as directory:
    temp = Path(directory)
    exe = temp / 'GuiguModTranslator.exe'
    shutil.copy2(ROOT / 'GuiguModTranslator.exe', exe)
    env = dict(os.environ, GUIGU_TRANSLATOR_DATA=str(temp / 'userdata'),
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    subprocess.run([str(exe), '--game', str(ROOT.parent), 'scan-destinies', '--output', str(temp / 'out')],
                   env=env, cwd=temp, timeout=120, check=True)
    report = json.loads((temp / 'out/untranslated-destinies.json').read_text(encoding='utf-8'))
    project = json.loads((temp / 'out/project.json').read_text(encoding='utf-8'))
    assert project['mod']['id'] == 'character-creation-destinies'
    assert len(project['units']) > 0
    result = {'result': 'passed', 'texts': len(project['units']), 'missing_texts': report['missing_texts'],
              'checks': ['copied standalone exe', 'isolated data folder', 'no Python in PATH',
                         'real destiny table scan', 'report and translation project saved']}
    (ROOT / 'evidence/frozen-destiny-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Frozen destiny scan passed')
