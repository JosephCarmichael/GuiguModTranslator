"""GitHub reads for releases and the shared library; credentials stay on this PC."""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app_config import data_dir

REPOSITORY = 'JosephCarmichael/GuiguModTranslator'
API_ROOT = 'https://api.github.com/repos/' + REPOSITORY
ACCESS_FILE = 'github-access.json'


def save_token(token):
    from api_access import _crypt
    from installer import atomic_bytes
    token = token.strip()
    if not re.fullmatch(r'(?:github_pat_|ghp_|gho_)[A-Za-z0-9_]{20,}', token):
        raise ValueError('Enter a GitHub personal access token that can read this repository.')
    protected = base64.b64encode(_crypt(token.encode('utf-8'))).decode('ascii')
    atomic_bytes(data_dir() / ACCESS_FILE, json.dumps({'protected_token': protected}).encode())


def load_token():
    path = data_dir() / ACCESS_FILE
    if not path.exists():
        return ''
    try:
        from api_access import _crypt
        value = json.loads(path.read_text(encoding='utf-8'))
        return _crypt(base64.b64decode(value['protected_token'], validate=True), decrypt=True).decode('utf-8')
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Saved GitHub access could not be read. Re-enter it in Options → GitHub access.') from None


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != 'https' or not (url.hostname == 'github.com' or url.hostname == 'api.github.com'
                                         or (url.hostname or '').endswith('.githubusercontent.com')):
            raise ValueError('GitHub returned an unexpected download location.')
        redirect = super().redirect_request(request, fp, code, msg, headers, newurl)
        if url.netloc != urllib.parse.urlsplit(request.full_url).netloc:
            redirect.remove_header('Authorization')
        return redirect


def open_request(url, *, binary=False, raw=False):
    if not url.startswith(API_ROOT + '/'):
        raise ValueError('The download does not belong to the configured GitHub repository.')
    headers = {'User-Agent': 'GuiguModTranslator',
               'Accept': ('application/vnd.github.raw+json' if raw else
                          'application/octet-stream' if binary else 'application/vnd.github+json'),
               'X-GitHub-Api-Version': '2022-11-28'}
    token = load_token()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(url, headers=headers)
    try:
        return urllib.request.build_opener(SafeRedirect()).open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403, 404):
            raise ValueError(f'GitHub HTTP {status}: check repository access in Options → GitHub access. '
                             'Private releases require an invited GitHub account and a read-only token.') from None
        raise ValueError(f'GitHub HTTP {status}. Try again later.') from None


def read_bytes(url, *, binary=False, limit=8 * 1024 * 1024):
    with open_request(url, binary=binary) as response:
        value = response.read(limit + 1)
    if len(value) > limit:
        raise ValueError('GitHub response exceeded the allowed size.')
    return value


def read_json(url, limit=8 * 1024 * 1024):
    return json.loads(read_bytes(url, limit=limit))


def repository_file(path, ref='main', limit=32 * 1024 * 1024):
    # The API's raw representation also works for private repositories.
    url = API_ROOT + '/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + urllib.parse.quote(ref, safe='')
    with open_request(url, raw=True) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('Shared translation file is too large.')
    return payload
