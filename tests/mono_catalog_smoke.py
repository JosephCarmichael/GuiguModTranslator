"""Run catalogue tests inside the game's actual embedded Mono, in a child process."""
import ctypes
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
game = root.parent
mono_dir = game / 'MelonLoader/Dependencies/MonoBleedingEdge.x64'
managed = game / 'MelonLoader/Managed'
os.add_dll_directory(str(mono_dir))
mono = ctypes.CDLL(str(mono_dir / 'mono-2.0-bdwgc.dll'))


def function(name, result, *arguments):
    method = getattr(mono, name)
    method.restype, method.argtypes = result, arguments
    return method


function('mono_set_dirs', None, ctypes.c_char_p, ctypes.c_char_p)(
    str(managed).encode(), str(mono_dir / 'etc').encode())
function('mono_set_assemblies_path', None, ctypes.c_char_p)(str(managed).encode())
function('mono_config_parse', None, ctypes.c_char_p)(None)
domain = function('mono_jit_init_version', ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p)(
    b'GuiguCatalogVerification', b'v4.0.30319')
assert domain, 'Mono domain could not start'
exe = root / 'runtime/CatalogTests.exe'
assembly = function('mono_domain_assembly_open', ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(domain, str(exe).encode())
assert assembly, 'Mono could not load catalogue tests'
values = [str(exe), str(game / 'UserData/GuiguModTranslator/installed.json'),
          str(game / 'UserData/GuiguModTranslator/destiny-inventory.json')]
argv = (ctypes.c_char_p * len(values))(*(s.encode() for s in values))
code = function('mono_jit_exec', ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                ctypes.POINTER(ctypes.c_char_p))(domain, assembly, len(values), argv)
print('Game Mono catalogue test exit:', code, flush=True)
assert code == 0
