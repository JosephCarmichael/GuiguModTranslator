import hashlib
import io
import json
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

import app_updates as updates
from github_client import API_ROOT, SafeRedirect


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch('app_updates.data_dir', return_value=self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def archive(self, extras=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('GuiguModTranslator/GuiguModTranslator.exe', b'new app')
            for name, content in (extras or {}).items():
                archive.writestr(name, content)
        return stream.getvalue()

    def metadata(self, payload):
        return {'version': '1.4.1', 'edition': 'friends', 'asset': {'id': 123},
                'sha256': hashlib.sha256(payload).hexdigest(), 'exe_sha256': hashlib.sha256(b'new app').hexdigest()}

    def test_each_edition_gets_its_own_newer_release(self):
        manifest = {'schema': 1, 'version': '1.4.1', 'editions': {edition: {
            'asset': edition + '.zip', 'sha256': 'a' * 64, 'exe_sha256': 'b' * 64} for edition in ('friends', 'personal')}}
        release = {'tag_name': 'v1.4.1', 'assets': [{'name': 'update-manifest.json', 'id': 1},
                   {'name': 'friends.zip', 'id': 2}, {'name': 'personal.zip', 'id': 3}]}
        with patch('app_updates.read_json', return_value=release), \
             patch('app_updates.read_bytes', return_value=json.dumps(manifest).encode()):
            self.assertEqual(updates.check_update('1.4.0', 'friends')['asset']['id'], 2)
            self.assertEqual(updates.check_update('1.4.0', 'personal')['asset']['id'], 3)
            self.assertIsNone(updates.check_update('1.4.1'))
            self.assertIsNone(updates.check_update('2.0.0'))
            release['prerelease'] = True
            self.assertIsNone(updates.check_update('1.4.0'))

    def test_missing_edition_and_mismatched_version_are_rejected(self):
        release = {'tag_name': 'v1.4.1', 'assets': [{'name': 'update-manifest.json', 'id': 1}]}
        for manifest in ({'schema': 1, 'version': '1.4.0'}, {'schema': 1, 'version': '1.4.1', 'editions': {}}):
            with self.subTest(manifest=manifest), patch('app_updates.read_json', return_value=release), \
                 patch('app_updates.read_bytes', return_value=json.dumps(manifest).encode()):
                with self.assertRaises(ValueError):
                    updates.check_update('1.4.0')

    def test_verified_archive_stages_only_the_executable(self):
        payload = self.archive({'GuiguModTranslator/START HERE.txt': b'help'})
        with patch('app_updates.open_request', return_value=io.BytesIO(payload)):
            staged = updates.prepare_update(self.metadata(payload))
        self.assertEqual(Path(staged['executable']).read_bytes(), b'new app')
        self.assertFalse((Path(staged['executable']).parent / 'download.zip').exists())

    def test_tampering_cancellation_and_traversal_leave_no_staged_app(self):
        for extra, bad_hash, cancelled in [({}, True, False), ({'../../outside': b'bad'}, False, False),
                                            ({'C:/outside': b'bad'}, False, False), ({}, False, True)]:
            payload = self.archive(extra)
            metadata = self.metadata(payload)
            if bad_hash:
                metadata['sha256'] = '0' * 64
            with self.subTest(extra=extra, cancelled=cancelled), patch('app_updates.open_request', return_value=io.BytesIO(payload)):
                with self.assertRaises((ValueError, InterruptedError)):
                    updates.prepare_update(metadata, stop=lambda: cancelled)
            self.assertEqual(list((self.root / 'updates').iterdir()), [])

    def test_wrong_executable_hash_is_rejected(self):
        payload = self.archive()
        metadata = {**self.metadata(payload), 'exe_sha256': '0' * 64}
        with patch('app_updates.open_request', return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(ValueError, 'executable checksum'):
                updates.prepare_update(metadata)

    def test_redirect_drops_token_before_leaving_github_api(self):
        request = urllib.request.Request(API_ROOT + '/releases/assets/1', headers={'Authorization': 'Bearer private'})
        redirect = SafeRedirect().redirect_request(request, None, 302, '', {}, 'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(redirect.get_header('Authorization'))
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(request, None, 302, '', {}, 'https://untrusted.test/file')

    def plan(self):
        stage = self.root / 'stage'
        stage.mkdir()
        source = stage / 'GuiguModTranslator.exe'
        source.write_bytes(b'new app')
        target = self.root / 'GuiguModTranslator.exe'
        target.write_bytes(b'old app')
        data = self.root / 'data'
        data.mkdir()
        (data / 'mod-titles.json').write_text('saved titles')
        plan = {'schema': 1, 'parent_pid': 1234, 'source': str(source), 'target': str(target),
                'data': str(data), 'sha256': hashlib.sha256(b'new app').hexdigest()}
        path = stage / 'install.json'
        path.write_text(json.dumps(plan))
        return path, target, data

    def test_install_waits_for_old_process_preserves_data_and_keeps_backup(self):
        path, target, data = self.plan()
        with patch('app_updates.wait_for_parent') as wait, patch('app_updates.subprocess.Popen') as launch:
            updates.apply_update(path)
        wait.assert_called_once_with(1234)
        self.assertEqual(target.read_bytes(), b'new app')
        self.assertEqual(target.with_suffix('.previous.exe').read_bytes(), b'old app')
        self.assertEqual((data / 'mod-titles.json').read_text(), 'saved titles')
        self.assertEqual(launch.call_args.kwargs['env']['GUIGU_TRANSLATOR_DATA'], str(data))

    def test_failed_restart_rolls_back_to_previous_executable(self):
        path, target, data = self.plan()
        with patch('app_updates.wait_for_parent'), patch('app_updates.subprocess.Popen', side_effect=OSError('locked')):
            with self.assertRaises(OSError):
                updates.apply_update(path)
        self.assertEqual(target.read_bytes(), b'old app')
        self.assertFalse((data / 'update-last.json').exists())

    def test_wait_failure_never_replaces_current_app(self):
        path, target, _ = self.plan()
        with patch('app_updates.wait_for_parent', side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                updates.apply_update(path)
        self.assertEqual(target.read_bytes(), b'old app')


if __name__ == '__main__':
    unittest.main()
