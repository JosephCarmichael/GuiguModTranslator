"""Reject local credentials and embedded API keys before distributing a build."""
import marshal
import re

PRIVATE_FILES = {'service.json', 'bundled_service.json', 'openrouter-access.json',
                 'github-access.json', 'translation-balances.json', 'preferences.json', '.env'}
KEY_PATTERN = re.compile(rb'(?:sk-or-v1-[a-f0-9]{64}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|AIza[A-Za-z0-9_-]{35})')


def verify_archive(archive):
    for name in archive.toc:
        normalized = name.replace('\\', '/').lower()
        if normalized.rsplit('/', 1)[-1] in PRIVATE_FILES or normalized.startswith('projects/'):
            raise ValueError('Private configuration found in executable: ' + name)
        payload = archive.extract(name)
        if payload and KEY_PATTERN.search(payload):
            raise ValueError('Credential-shaped content found in executable: ' + name)
        if normalized.endswith('.pyz'):
            modules = archive.open_embedded_archive(name)
            for module in modules.toc:
                value = modules.extract(module)
                if value is not None and KEY_PATTERN.search(marshal.dumps(value)):
                    raise ValueError('Credential-shaped content found in module: ' + module)
    return True
