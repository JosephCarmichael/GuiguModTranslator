import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api_access
import app_config
from release_security import verify_archive


class Archive:
    def __init__(self, data):
        self.toc = data

    def extract(self, name):
        return self.toc[name]


class ReleaseSecurityTests(unittest.TestCase):
    def test_private_files_are_rejected_even_without_a_key_value(self):
        for name in ('bundled_service.json', 'service.json', 'nested/openrouter-access.json',
                     'github-access.json', 'projects/private.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Private configuration'):
                verify_archive(Archive({name: b'{}'}))

    def test_key_in_an_unexpected_asset_is_rejected_without_logging_it(self):
        key = b'sk-or-v1-' + b'a' * 64
        with self.assertRaisesRegex(ValueError, 'unexpected.txt') as failure:
            verify_archive(Archive({'unexpected.txt': b'prefix ' + key}))
        self.assertNotIn(key.decode(), str(failure.exception))

    def test_embedded_python_constants_are_scanned(self):
        key = 'sk-or-v1-' + 'a' * 64
        outer = Archive({'PYZ.pyz': b'compressed'})
        inner = Archive({'module': compile('value = ' + repr(key), '<test>', 'exec')})
        outer.open_embedded_archive = lambda _: inner
        with self.assertRaisesRegex(ValueError, 'module'):
            verify_archive(outer)

    def test_keyless_archive_passes(self):
        self.assertTrue(verify_archive(Archive({'build_policy.json': b'{"edition":"public"}',
                                               'runtime/loader.dll': b'own loader'})))

    def test_own_key_is_accepted_without_a_shared_key_and_removal_blocks_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('api_access.data_dir', return_value=root), patch('app_config.data_dir', return_value=root), \
                 patch('api_access.RESOURCE_DIR', root), patch('app_config.RESOURCE_DIR', root), \
                 patch('api_access._crypt', side_effect=lambda data, decrypt=False: data):
                key = 'sk-or-personal-fixture-key-only'
                api_access.save_openrouter_key(key)
                self.assertTrue(app_config.service_profile(mode='paid')['personal_key'])
                (root/'service.json').write_text(json.dumps({'api_key': key}))
                api_access.remove_openrouter_key()
                with self.assertRaisesRegex(ValueError, 'No translation key'):
                    app_config.service_profile(mode='paid')
                self.assertTrue(app_config.service_profile(mode='google')['keyless'])
