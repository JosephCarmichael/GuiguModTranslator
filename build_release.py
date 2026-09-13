"""Build Windows-only self-contained executables and a minimal friends ZIP."""
import hashlib
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def build(onefile, output_dir=None):
    name = 'GuiguModTranslator' if onefile else 'GuiguModTranslatorPreview'
    mode = 'onefile' if onefile else 'onedir'
    output_dir = Path(output_dir) if output_dir else ROOT/'dist'
    args = [sys.executable, '-X', 'utf8', '-m', 'PyInstaller', '--noconfirm', '--clean', '--'+mode,
            '--windowed', '--name', name, '--collect-all', 'UnityPy',
            '--add-data', str(ROOT/'bundled_service.json')+';.',
            '--add-data', str(ROOT/'runtime/GuiguModTranslation.dll')+';runtime',
            '--add-data', str(ROOT/'runtime/manifest.json')+';runtime',
            '--workpath', str(Path(tempfile.gettempdir())/('guigu-build-'+mode)),
            '--distpath', str(output_dir), '--specpath', str(ROOT/'build'), str(ROOT/'entry.py')]
    with (ROOT/'projects'/('build-'+mode+'.log')).open('w',encoding='utf-8') as log:
        subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    return output_dir/(name+'.exe') if onefile else output_dir/name/(name+'.exe')

def verify(exe, name, live=False):
    # No Python environment, installation directories or saved local key are
    # required. All third-party modules must load from the executable bundle.
    with tempfile.TemporaryDirectory(prefix='Guigu Portable Test ') as folder:
        temp=Path(folder)
        env=dict(os.environ)
        for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):
            env.pop(key,None)
        env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        env['GUIGU_TRANSLATOR_DATA']=str(temp/'userdata')
        if exe.parent.name=='GuiguModTranslatorPreview':
            target=temp/'app'
            shutil.copytree(exe.parent,target)
            copied=target/exe.name
        else:
            copied=temp/exe.name
            shutil.copy2(exe,copied)
        report=ROOT/'projects'/(name+'.json')
        flag='--self-test-live' if live else '--self-test'
        subprocess.run([str(copied),flag,str(report)],cwd=temp,env=env,timeout=180,check=True)
        result=json.loads(report.read_text(encoding='utf-8'))
        if result['result']!='passed' or not result['frozen'] or result['provider']!='OpenRouter':
            raise RuntimeError('Portable executable validation failed')
        print(name+': passed',flush=True)

def package(exe, side_by_side=False):
    from PyInstaller.archive.readers import CArchiveReader
    contents=CArchiveReader(str(exe))
    embedded=json.loads(contents.extract('bundled_service.json').decode('utf-8'))
    expected=json.loads((ROOT/'bundled_service.json').read_text(encoding='utf-8'))
    assert embedded==expected
    assert not any(name.replace('\\','/').endswith('/service.json') or name=='service.json'
                   or name.replace('\\','/').startswith('projects/') for name in contents.toc)
    suffix = '-Updated-'+datetime.now().strftime('%Y%m%d-%H%M%S') if side_by_side else ''
    destination=ROOT/'release'/('GuiguModTranslator'+suffix)
    destination.mkdir(parents=True,exist_ok=True)
    try:
        shutil.copy2(exe,destination/'GuiguModTranslator.exe')
    except PermissionError:
        # An open portable app must not be stopped to publish its replacement.
        destination=ROOT/'release'/('GuiguModTranslator-Updated-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        destination.mkdir(parents=True,exist_ok=False)
        shutil.copy2(exe,destination/'GuiguModTranslator.exe')
        print('Previous release is running; updated app: '+str(destination),flush=True)
    if not side_by_side:
        shutil.copy2(exe,ROOT/'GuiguModTranslator.exe')
    (destination/'Launch.bat').write_text('@echo off\r\nstart "" "%~dp0GuiguModTranslator.exe"\r\n',encoding='ascii')
    (destination/'START HERE.txt').write_text(
        'GUIGU MOD TRANSLATOR\n\n'
        '1. Extract this ZIP to a folder.\n'
        '2. Double-click GuiguModTranslator.exe (or Launch.bat).\n'
        '3. Select a mod and click Translate and install.\n'
        '4. Restart the game to use the translations.\n\n'
        'Parallel requests controls simultaneous batches: 16 (default), 32, 64,\n'
        'or 128; smaller options are also available. The app remembers your choice.\n'
        'Speed depends on service capacity; rate limits are retried automatically.\n\n'
        'Entries per request selects 12, 24, 48 (default), or 96 text entries.\n'
        'The app retains a 6,000-character target and splits truncated batches.\n'
        'Existing translations are reused when changing provider or batch size.\n\n'
        'Text conflicts resolve automatically: the latest installed translation wins.\n'
        'Removing it restores the other installed mod’s wording. Manual edits win\n'
        'over machine translations when duplicate text occurs within a project.\n\n'
        'If the provider is busy, the app reduces actual concurrency and shows a\n'
        'retry countdown. The selected number remains the maximum. Errors and\n'
        'retries are recorded in request-errors.jsonl inside the saved project.\n\n'
        'Python and all required packages are included. No Python installation,\n'
        'package downloads, API-key entry or administrator access is required.\n'
        'Requires 64-bit Windows 10/11, an internet connection and downloaded\n'
        'Tale of Immortal mods. Translation access is already configured.\n\n'
        'The app finds Steam automatically. If it cannot find the game, use\n'
        'Options > Choose game folder and select the folder with guigubahuang.exe.\n\n'
        'The app installs its text loader and translated dictionaries into the game.\n'
        'Options > Install saved translations applies work you already translated.\n'
        'Options > Remove selected mod’s translations reverses the installation.\n'
        'Requires the game’s bundled MelonLoader 0.5.x. Start the game once first.\n'
        'The detailed editor is under Options. Progress is saved automatically.\n'
        'If the shared allowance runs out, saved work remains available.\n\n'
        'Saved files: %LOCALAPPDATA%\\GuiguModTranslator\\projects\n',encoding='utf-8')
    # Retain package license texts alongside the executable.
    site=Path(sys.prefix)/'Lib/site-packages'
    notices=[]
    for dist in sorted(site.glob('*.dist-info')):
        for p in sorted(dist.rglob('*')):
            if p.is_file() and any(word in p.name.lower() for word in ('license','copying','notice')):
                notices.append('\n\n'+str(p.relative_to(site))+'\n'+p.read_text(encoding='utf-8',errors='replace'))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        notices.append('\n\nPython\n'+python_license.read_text(encoding='utf-8',errors='replace'))
    (destination/'THIRD PARTY LICENSES.txt').write_text('Bundled runtime and dependency license texts\n'+''.join(notices),encoding='utf-8')
    archive=ROOT/'release'/('GuiguModTranslator-Friends'+suffix+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for filename in ('GuiguModTranslator.exe','Launch.bat','START HERE.txt','THIRD PARTY LICENSES.txt'):
            z.write(destination/filename,arcname='GuiguModTranslator/'+filename)
    result={'zip':str(archive),'executable':str(destination/'GuiguModTranslator.exe'),'side_by_side':side_by_side,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files':zipfile.ZipFile(archive).namelist(),'model':'deepseek/deepseek-v4.1-flash'}
    (ROOT/'projects/release-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('ZIP ready: '+str(archive),flush=True)

def verify_real_mod(exe):
    with tempfile.TemporaryDirectory(prefix='Guigu Real Mod Test ') as directory:
        temp=Path(directory)
        env=dict(os.environ)
        env['GUIGU_TRANSLATOR_DATA']=str(temp/'userdata')
        env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        output=temp/'out'
        process=subprocess.run([str(exe),'extract','2859071194','--output',str(output)],
                               cwd=temp,env=env,timeout=120)
        if process.returncode:
            error=temp/'userdata/last-error.log'
            if error.exists():
                shutil.copy2(error,ROOT/'projects/frozen-real-mod-error.log')
            raise RuntimeError('Real mod extraction failed in the executable')
        project=json.loads((output/'2859071194/project.json').read_text(encoding='utf-8'))
        assert len(project['units'])>1900 and not project['coverage']['counts'].get('unreadable')
        result={'result':'passed','mod':'2859071194','strings':len(project['units']),
                'coverage':project['coverage']['counts'],
                'checks':['real encoded mod','managed DLL','Excel sheets','Unity bundles','Chinese output encoding']}
        (ROOT/'projects/frozen-real-mod-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('frozen-real-mod-check: passed',flush=True)

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Skip paid live API checks')
    parser.add_argument('--side-by-side', action='store_true', help='Build new paths without replacing existing executables or ZIPs')
    args = parser.parse_args()
    from app_config import installed_game
    game = installed_game()
    if game is None:
        raise RuntimeError('A local game installation is required to build the runtime loader.')
    (ROOT/'projects').mkdir(exist_ok=True)
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(ROOT/'loader/Build.ps1'), '-GameRoot', str(game), '-Test'], check=True)
    output = ROOT/'dist'/('update-'+datetime.now().strftime('%Y%m%d-%H%M%S')) if args.side_by_side else ROOT/'dist'
    preview=build(False, output)
    verify(preview,'frozen-onedir-check')
    final=build(True, output)
    verify(final,'frozen-onefile-check')
    verify_real_mod(final)
    if not args.offline:
        verify(final,'frozen-openrouter-live-check',live=True)
    package(final, side_by_side=args.side_by_side)
