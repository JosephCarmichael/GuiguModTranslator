"""Build interfaces from real native game data using only the shipped setup tools.
No game launch, no existing managed assemblies, no downloads or paid requests.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_config import installed_game, RESOURCE_DIR
from game_setup import setup_plan, install_files, GENERATOR
from installer import preflight

source = installed_game()
with tempfile.TemporaryDirectory(prefix='Guigu Clean Setup ') as directory:
    game = Path(directory)
    for name in ('guigubahuang.exe', 'GameAssembly.dll', 'guigubahuang_Data/globalgamemanagers',
                 'guigubahuang_Data/il2cpp_data/Metadata/global-metadata.dat'):
        target = game / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    pending, generation = setup_plan(game)
    assert generation and 'version.dll' in pending
    values = []
    install_files(game, pending, lambda p, m: values.append(p), lambda: False)
    assert not (game / 'MelonLoader/Managed/Assembly-CSharp.dll').exists()
    tools = game / GENERATOR
    output = game / 'generated'
    commands = [
        ([str(tools / 'Cpp2IL/Cpp2IL.exe'), '--game-path', str(game), '--exe-name', 'guigubahuang',
          '--use-processor', 'attributeinjector', '--output-as', 'dummydll'], tools / 'Cpp2IL'),
        ([str(tools / 'Il2CppAssemblyUnhollower/AssemblyUnhollower.exe'),
          '--input=' + str(tools / 'Cpp2IL/cpp2il_out'), '--output=' + str(output),
          '--mscorlib=' + str(game / 'MelonLoader/Managed/mscorlib.dll'),
          '--unity=' + str(tools / 'UnityDependencies'), '--gameassembly=' + str(game / 'GameAssembly.dll'),
          '--add-prefix-to=ICSharpCode', '--add-prefix-to=Newtonsoft', '--add-prefix-to=TinyJson',
          '--add-prefix-to=Valve.Newtonsoft'], tools / 'Il2CppAssemblyUnhollower')]
    started = time.time()
    for i, (command, cwd) in enumerate(commands):
        print('Running bundled first-launch tool', i + 1, flush=True)
        with (RESOURCE_DIR / f'evidence/cold-setup-tool-{i+1}.log').open('w', encoding='utf-8') as log:
            subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
    for file in output.iterdir():
        if file.is_file():
            shutil.copy2(file, game / 'MelonLoader/Managed' / file.name)
    assert preflight(game)
    second, generation = setup_plan(game)
    assert not generation and not second, list(second)
    result = {'result': 'passed', 'elapsed_seconds': round(time.time() - started, 1),
              'installed_files': len(pending), 'generated_files': len(list(output.iterdir())),
              'checks': ['real native game data', 'clean install using bundled assets', 'no pre-generated game assemblies',
                         'Cpp2IL and Unhollower succeed offline', 'runtime preflight', 'repeat setup changes nothing'],
              'limits': 'The game was not launched by this test.'}
    (RESOURCE_DIR / 'evidence/cold-setup-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
