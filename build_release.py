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

def build(onefile, output_dir=None, edition="friends"):
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
            '--add-data', str(ROOT/'bundled_service.json')+';.',
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

def verify(exe, name, live=False, edition="friends"):
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

def package(exe, side_by_side=False, edition="friends"):
    from PyInstaller.archive.readers import CArchiveReader
    contents=CArchiveReader(str(exe))
    embedded=json.loads(contents.extract('bundled_service.json').decode('utf-8'))
    expected=json.loads((ROOT/'bundled_service.json').read_text(encoding='utf-8'))
    assert embedded==expected
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
        '1. Extract this ZIP to a folder.\n'
        '2. Double-click GuiguModTranslator.exe (or Launch.bat).\n'
        '3. Watch the setup bar. The app finds your installed Steam game, sets up\n'
        '   MelonLoader and the translator, and starts the game when needed.\n'
        '   The first launch can take several minutes.\n'
        '4. Choose Translate destiny menu, or select a mod and click Translate\n'
        '   and install. Close the game and use Launch game to apply changes.\n\n'
        'No loader installation, file copying, Python setup or API-key entry.\n'
        'Updates appear in the app when a new GitHub release is ready. Click\n'
        'Install update to download, verify and restart; your saved work stays.\n'
        'For private releases, use Options > GitHub access once with your own\n'
        'read-only token after the repository owner invites your account.\n'
        'GitHub access is separate from your translation API key.\n\n'
        'Mod preview images come from your installed mods. Select a mod to\n'
        'see its saved progress. Translate mod again makes new paid requests\n'
        'using your settings and saves a backup of the previous translation.\n'
        'Matching shared translations and titles are reused automatically.\n\n'
        'If Windows asks for permission, click Yes. Missing Microsoft runtimes\n'
        'are installed automatically; Windows may require a PC restart.\n'
        'If the game is already open and files need updating, save and close it.\n'
        'Setup continues automatically. Retry setup resumes interrupted work.\n\n'
        'LAUNCH FIX (1.3.2): If setup asks, choose Steam > Exit, not just X.\n'
        'The app repairs the Chinese game-folder name, then restarts Steam.\n'
        'Keep this translator in Downloads or another folder outside the game.\n'
        'Game files, saves, mods and existing translations are preserved.\n\n'
        'PERSONAL API KEY (1.3.3): Click API key or Options > API key.\n'
        'Paste your own OpenRouter key and click Save personal key.\n'
        'Translations then use your OpenRouter credit, with no app cost cap.\n'
        'Use shared key removes the saved personal key and restores the shared cap.\n'
        'Your key is encrypted for your Windows account and stays on your PC.\n\n'
        'Need help? Click What does this mean? beside API key for signup, credit,\n'
        'saved-translation and insufficient-funds instructions.\n\n'
        'TRANSLATE ALL (1.3.5): Set the slider from 5p to GBP 2 per mod, then\n'
        'click Translate all. Matching mods run cheapest first. The displayed\n'
        'combined estimate can exceed the slider value: the filter is per mod.\n'
        'The shared-key cap still applies; your personal key lifts that cap.\n'
        'Cancel all keeps saved progress. Repeating reuses existing translations.\n'
        'App updates keep saved translations in the same Windows user-data folder.\n\n'
        'MOD TITLES (1.3.8): Chinese mod names are translated to English and saved\n'
        'on this PC, so later launches cost nothing. A tick beside a mod means it\n'
        'already has a complete saved translation.\n\n'
        'BALANCE (1.3.6): The top-left balance shows your OpenRouter key allowance\n'
        'as a GBP estimate, with the original dollar amount underneath. It drops\n'
        'as billed responses arrive and refreshes from OpenRouter. Saved text\n'
        'costs nothing to reuse. Some unlimited keys do not expose a balance.\n\n'
        'If something goes wrong, click Collect logs in the app. It copies the\n'
        'report to your clipboard and saves Guigu-Logs.txt beside the EXE.\n'
        'Paste the report to send it, or send that text file. No log ZIP needed.\n\n'
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
        'Python, MelonLoader 0.5.4 and its first-launch tools are included.\n'
        'Requires 64-bit Windows 10/11, an internet connection and downloaded\n'
        'Tale of Immortal mods. Translation access is already configured.\n\n'
        'You need to own Tale of Immortal; the game itself is not in this ZIP.\n'
        'The app finds Steam automatically. If it cannot find the game, use\n'
        'Options > Choose game folder and select the folder with guigubahuang.exe.\n\n'
        'The app installs its text loader and translated dictionaries into the game.\n'
        'Options > Install saved translations applies work you already translated.\n'
        'Options > Remove selected mod’s translations reverses the installation.\n'
        'An existing compatible MelonLoader installation and other mods are kept.\n'
        'The detailed editor is under Options. Progress is saved automatically.\n'
        'If the shared allowance runs out, saved work remains available.\n\n'
        'Saved files: %LOCALAPPDATA%\\GuiguModTranslator\\projects\n',encoding='utf-8')
    with (destination/'START HERE.txt').open('a', encoding='utf-8') as instructions:
        instructions.write('\nEDITION: '+edition.upper()+'\n')
        instructions.write('Full-mod cost estimates appear beside each mod, in pence (p).\n')
        if edition == 'friends':
            instructions.write('The shared key allows full translation up to 5p (GBP 0.05). A personal OpenRouter key removes this app limit.\n')
        instructions.write('Translate destiny menu is always exempt from this limit.\n')
        instructions.write('Estimates cover all extracted text, even on resume. See Options > About cost estimates.\n')
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
    parser.add_argument('--edition', choices=('friends', 'personal'), default='friends')
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
