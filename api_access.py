"""User-supplied OpenRouter credentials, protected with Windows user DPAPI."""
import base64
import ctypes
import hmac
import json
import os
import re
from ctypes import wintypes

from app_config import RESOURCE_DIR, data_dir

ACCESS_FILE = 'openrouter-access.json'


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Saving a personal API key requires Windows.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, result = Blob(len(data), buffer), Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # No machine-wide flag: only the Windows user who saved the key can read it.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError('Windows could not read or save your API key. Enter it again in API key settings.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def bundled_key():
    try:
        return str(json.loads((RESOURCE_DIR / 'bundled_service.json').read_text(encoding='utf-8')).get('api_key', '')).strip()
    except (OSError, ValueError, AttributeError):
        return ''


def is_personal_key(key):
    shared = bundled_key()
    return bool(key.startswith('sk-or-') and (not shared or not hmac.compare_digest(key.encode(), shared.encode())))


def save_openrouter_key(key):
    key = key.strip()
    if not re.fullmatch(r'sk-or-[A-Za-z0-9_-]{16,}', key):
        raise ValueError('Paste your OpenRouter API key beginning with sk-or-.')
    if not is_personal_key(key):
        raise ValueError('This is not a separate personal key. The bundled shared key keeps its cost limit.')
    protected = base64.b64encode(_crypt(key.encode('utf-8'))).decode('ascii')
    from installer import atomic_bytes
    atomic_bytes(data_dir() / ACCESS_FILE,
                 json.dumps({'mode': 'personal', 'protected_key': protected}).encode('utf-8'))


def use_shared_key():
    # An explicit shared selection also overrides any legacy service.json.
    from installer import atomic_bytes
    atomic_bytes(data_dir() / ACCESS_FILE, b'{"mode":"shared"}')


def remove_openrouter_key():
    # A marker prevents an old service.json from silently reactivating a key.
    from installer import atomic_bytes
    atomic_bytes(data_dir() / ACCESS_FILE, b'{"mode":"none"}')


def selected_key():
    """None means legacy configuration; corrupt personal settings never fall back."""
    path = data_dir() / ACCESS_FILE
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['mode'] == 'none':
            return ''
        if value['mode'] == 'shared':
            return bundled_key()
        if value['mode'] != 'personal':
            raise ValueError()
        key = _crypt(base64.b64decode(value['protected_key'], validate=True), decrypt=True).decode('utf-8')
        if not re.fullmatch(r'sk-or-[A-Za-z0-9_-]{16,}', key):
            raise ValueError()
        return key
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        raise ValueError('Your saved OpenRouter key could not be read. Open API key settings and enter it again, '
                         'or choose Use shared key.') from None


def using_personal_key():
    from app_config import service_profile
    try:
        return service_profile().get('personal_key', False)
    except (OSError, ValueError):
        return False
