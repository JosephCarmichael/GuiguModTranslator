import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import windows_prerequisites as runtimes


class PrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.missing = self.patch('windows_prerequisites.missing_runtimes', side_effect=[['Visual C++'], []])
        self.patch('windows_prerequisites.ctypes.windll').shell32.IsUserAnAdmin.return_value = True
        self.signature = self.patch('windows_prerequisites.verify_microsoft_signature')
        response = io.BytesIO(b'MZfixture'); response.headers = {'Content-Length': '9'}
        self.download = self.patch('windows_prerequisites.urllib.request.urlopen', return_value=response)
        self.process = Mock(returncode=0); self.process.poll.return_value = 0
        self.launch = self.patch('windows_prerequisites.subprocess.Popen', return_value=self.process)

    def patch(self, *args, **kwargs):
        p = patch(*args, **kwargs); self.addCleanup(p.stop); return p.start()

    def test_existing_runtimes_do_not_download_or_launch_anything(self):
        self.missing.side_effect = None; self.missing.return_value = []
        runtimes.ensure_prerequisites(lambda *_: None, lambda: False)
        self.download.assert_not_called(); self.launch.assert_not_called()

    def test_missing_runtime_is_verified_before_silent_install(self):
        order = []
        self.signature.side_effect = lambda _: order.append('verify')
        self.launch.side_effect = lambda *_: (order.append('install') or self.process)
        runtimes.ensure_prerequisites(lambda *_: None, lambda: False)
        self.assertEqual(order, ['verify', 'install'])
        self.assertEqual(self.launch.call_args.args[0][1:], ['/install', '/quiet', '/norestart'])

    def test_signature_failure_never_executes_download(self):
        self.signature.side_effect = ValueError('invalid Microsoft signature')
        with self.assertRaisesRegex(ValueError, 'signature'):
            runtimes.ensure_prerequisites(lambda *_: None, lambda: False)
        self.launch.assert_not_called()

    def test_windows_restart_required_is_reported_without_rebooting(self):
        self.process.returncode = 3010
        with self.assertRaisesRegex(ValueError, 'Restart your PC'):
            runtimes.ensure_prerequisites(lambda *_: None, lambda: False)
        self.assertEqual(self.launch.call_count, 1)

    def test_cancelled_download_is_not_executed(self):
        with self.assertRaises(InterruptedError):
            runtimes.ensure_prerequisites(lambda *_: None, lambda: True)
        self.launch.assert_not_called(); self.signature.assert_not_called()

    def test_failed_installer_does_not_report_success(self):
        self.process.returncode = 1603
        with self.assertRaisesRegex(ValueError, '1603'):
            runtimes.ensure_prerequisites(lambda *_: None, lambda: False)


if __name__ == '__main__': unittest.main()
