"""Build Windows-only self-contained executables and a credential-free public ZIP."""
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

def build(onefile, output_dir=None, edition="public"):
    name = 'GuiguModTranslator' if onefile else 'GuiguModTranslatorPreview'
    mode = 'onefile' if onefile else 'onedir'
    output_dir = Path(output_dir) if output_dir else ROOT/'dist'
    build_id = edition + '-' + hashlib.sha256(str(output_dir.resolve()).encode()).hexdigest()[:12]
    policy = ROOT/'build'/build_id/'build_policy.json'
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(json.dumps({'edition': edition}), encoding='utf-8')
    runtime = policy.parent/'runtime'
    runtime.mkdir(exist_ok=True)
    payload = (ROOT/'runtime/GuiguModTranslation.dll').read_bytes()
    manifest = (ROOT/'runtime/manifest.json').read_bytes()
    assert hashlib.sha256(payload).hexdigest() == json.loads(manifest)['sha256']
    (runtime/'GuiguModTranslation.dll').write_bytes(payload)
    (runtime/'manifest.json').write_bytes(manifest)
    from game_setup import verify_assets
    verify_assets(ROOT/'bootstrap')
    bootstrap = policy.parent/'bootstrap'
    shutil.copytree(ROOT/'bootstrap', bootstrap, dirs_exist_ok=True)
    args = [sys.executable, '-X', 'utf8', '-m', 'PyInstaller', '--noconfirm', '--clean', '--'+mode,
            '--windowed', '--name', name, '--collect-all', 'UnityPy',
            '--add-data', str(policy)+';.',
            '--add-data', str(runtime/'GuiguModTranslation.dll')+';runtime',
            '--add-data', str(runtime/'manifest.json')+';runtime',
            '--add-data', str(bootstrap)+';bootstrap',
            '--add-data', str(ROOT/'shared-library')+';shared-library',
            '--workpath', str(Path(tempfile.gettempdir())/('guigu-build-'+build_id+'-'+mode)),
            '--distpath', str(output_dir), '--specpath', str(policy.parent), str(ROOT/'entry.py')]
    with (ROOT/'projects'/('build-'+mode+'.log')).open('w',encoding='utf-8') as log:
        subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    return output_dir/(name+'.exe') if onefile else output_dir/name/(name+'.exe')

def verify(exe, name, live=False, edition="public"):
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
        assert result['edition'] == edition
        print(name+': passed',flush=True)

def package(exe, side_by_side=False, edition="public"):
    from PyInstaller.archive.readers import CArchiveReader
    contents=CArchiveReader(str(exe))
    from release_security import verify_archive
    verify_archive(contents)
    assert json.loads(contents.extract('build_policy.json')) == {'edition': edition}
    assert not any(name.replace('\\','/').endswith('/service.json') or name=='service.json'
                   or name.replace('\\','/').endswith(('openrouter-access.json', 'github-access.json', 'translation-balances.json'))
                   or name.replace('\\','/').startswith('projects/') for name in contents.toc)
    suffix = '-Updated-'+datetime.now().strftime('%Y%m%d-%H%M%S') if side_by_side else ''
    destination=ROOT/'release'/('GuiguModTranslator-'+edition.title()+suffix)
    destination.mkdir(parents=True,exist_ok=True)
    try:
        shutil.copy2(exe,destination/'GuiguModTranslator.exe')
    except PermissionError:
        # An open portable app must not be stopped to publish its replacement.
        destination=ROOT/'release'/('GuiguModTranslator-Updated-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        destination.mkdir(parents=True,exist_ok=False)
        shutil.copy2(exe,destination/'GuiguModTranslator.exe')
        print('Previous release is running; updated app: '+str(destination),flush=True)
    if not side_by_side and edition == 'personal':
        shutil.copy2(exe,ROOT/'GuiguModTranslator.exe')
    (destination/'Launch.bat').write_text('@echo off\r\nstart "" "%~dp0GuiguModTranslator.exe"\r\n',encoding='ascii')
    (destination/'START HERE.txt').write_text(
        'GUIGU MOD TRANSLATOR\n\n'
        '1. Extract this ZIP outside the game folder and open GuiguModTranslator.exe.\n'
        '2. Let automatic Steam game and translation-plugin setup finish.\n'
        '3. Choose a provider in Translation models.\n'
        '   Google Translate: no key, experimental web service; may be throttled.\n'
        '   OpenRouter Free: your own key, account-wide daily quotas.\n'
        '   OpenRouter Paid: your own key and credit.\n'
        '4. Select a mod, choose Translate and install, then restart the game.\n\n'
        'No API keys are included. Your own keys are saved encrypted on this PC.\n'
        'Matching saved/shared translations are reused without requests.\n'
        'Progress is saved; resume after a connection failure or service limit.\n'
        'Updates are offered at startup and installed only when you choose.\n'
        'Saved work remains in %LOCALAPPDATA%\\GuiguModTranslator.\n'
        'The shared library downloads published text; it does not upload projects.\n\n'
        'Requires 64-bit Windows 10/11, internet, and an owned Steam game.\n'
        'Python and setup tools are included. Windows permission may be required.\n'
        'Use Options > Choose game folder if detection fails, or Collect logs for help.\n'
        'Private GitHub downloads need Options > GitHub access.\n'
        'See https://github.com/JosephCarmichael/GuiguModTranslator for the user guide.\n',
        encoding='utf-8')
    # Retain package license texts alongside the executable.
    site=Path(sys.prefix)/'Lib/site-packages'
    notices=[]
    notices.append('\n\nMelonLoader and first-launch tools\n'+(ROOT/'bootstrap/THIRD PARTY.txt').read_text(encoding='utf-8'))
    for dist in sorted(site.glob('*.dist-info')):
        for p in sorted(dist.rglob('*')):
            if p.is_file() and any(word in p.name.lower() for word in ('license','copying','notice')):
                notices.append('\n\n'+str(p.relative_to(site))+'\n'+p.read_text(encoding='utf-8',errors='replace'))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        notices.append('\n\nPython\n'+python_license.read_text(encoding='utf-8',errors='replace'))
    (destination/'THIRD PARTY LICENSES.txt').write_text('Bundled runtime and dependency license texts\n'+''.join(notices),encoding='utf-8')
    shutil.copy2(ROOT/'third_party/THIRD PARTY SOURCES.zip', destination/'THIRD PARTY SOURCES.zip')
    archive=ROOT/'release'/('GuiguModTranslator-'+edition.title()+suffix+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for filename in ('GuiguModTranslator.exe','Launch.bat','START HERE.txt','THIRD PARTY LICENSES.txt','THIRD PARTY SOURCES.zip'):
            z.write(destination/filename,arcname='GuiguModTranslator/'+filename)
    result={'edition':edition,'zip':str(archive),'executable':str(destination/'GuiguModTranslator.exe'),'side_by_side':side_by_side,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files':zipfile.ZipFile(archive).namelist(),'model':'deepseek/deepseek-v4.1-flash'}
    for name in ('release-manifest.json', 'release-manifest-'+edition+'.json'):
        (ROOT/'projects'/name).write_text(json.dumps(result,indent=2),encoding='utf-8')
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
    parser.add_argument('--edition', choices=('public', 'friends', 'personal'), default='public')
    parser.add_argument('--use-prebuilt-runtime', action='store_true', help='Use the verified own-code runtime for hosted builds without a game installation')
    args = parser.parse_args()
    from app_config import installed_game
    game = installed_game()
    if game is None and not args.use_prebuilt_runtime:
        raise RuntimeError('A local game installation is required to build the runtime loader.')
    (ROOT/'projects').mkdir(exist_ok=True)
    if args.use_prebuilt_runtime:
        from runtime_bundle import restore_runtime
        restore_runtime()
    else:
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(ROOT/'loader/Build.ps1'), '-GameRoot', str(game), '-Test'], check=True)
    output = ROOT/'dist'/(args.edition+'-update-'+datetime.now().strftime('%Y%m%d-%H%M%S')) if args.side_by_side else ROOT/'dist'
    preview=build(False, output, args.edition)
    verify(preview,'frozen-onedir-check', edition=args.edition)
    final=build(True, output, args.edition)
    verify(final,'frozen-onefile-check', edition=args.edition)
    if not args.use_prebuilt_runtime:
        verify_real_mod(final)
    if not args.offline:
        verify(final,'frozen-openrouter-live-check',live=True,edition=args.edition)
    package(final, side_by_side=args.side_by_side, edition=args.edition)
