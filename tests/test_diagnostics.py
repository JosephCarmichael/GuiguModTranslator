import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostics as d


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root/'Chinese game 鬼谷八荒'; self.game.mkdir()
        self.app = self.root/'app'; self.app.mkdir()
        self.player = self.root/'player'; self.player.mkdir()

    def report(self):
        with patch('diagnostics.windows_events', return_value='crash fixture'), patch('diagnostics.steam_root', return_value=None):
            return d.build_report(self.game, {'message':'50% Starting game'}, self.app, self.player)

    def test_report_includes_unicode_path_live_state_and_missing_files(self):
        (self.player/'Player.log').write_text('menu followed by crash 中文', encoding='utf-8')
        value = self.report()
        for text in ('鬼谷八荒', '50% Starting game', 'crash fixture', 'menu followed by crash 中文', 'Not present:', 'Modified UTC:'):
            self.assertIn(text, value)

    def test_service_and_saved_translations_are_not_collected_and_keys_are_redacted(self):
        (self.app/'service.json').write_text('{"api_key":"private-service-sentinel"}')
        (self.app/'openrouter-access.json').write_text('{"protected_key":"private-encrypted-key-sentinel"}')
        store = self.game/'UserData/GuiguModTranslator'; store.mkdir(parents=True)
        (store/'installed.json').write_text('private-translation-sentinel')
        (self.app/'last-error.log').write_text('Authorization: Bearer secretcredential\napi_key="secret-value"\nsk-or-v1-1234567890123456')
        value = self.report()
        for secret in ('private-encrypted-key-sentinel', 'private-service-sentinel','private-translation-sentinel','secretcredential','secret-value','sk-or-v1-1234567890123456'):
            self.assertNotIn(secret, value)
        self.assertIn('[REDACTED', value)

    def test_large_log_reads_tail_and_marks_truncation(self):
        path = self.player/'Player.log'; path.write_bytes(b'beginning' + b'x'*d.LOG_LIMIT + b'last crash')
        value = d.log_text(path)
        self.assertIn('[Showing last', value); self.assertTrue(value.endswith('last crash'))
        self.assertNotIn('beginning', value)

    def test_writes_plain_text_next_to_exe_and_copies_identical_report(self):
        with patch('diagnostics.APP_DIR', self.app), patch('diagnostics.build_report', return_value='Report 中文') as build, \
             patch('diagnostics.copy_to_clipboard') as copy:
            result = d.collect_logs(self.game, {'busy':True}, 123)
        self.assertEqual(Path(result['path']).parent, self.app)
        self.assertEqual(Path(result['path']).read_text(encoding='utf-8-sig'), 'Report 中文')
        copy.assert_called_once_with('Report 中文', 123)
        self.assertTrue(result['copied'])
        self.assertEqual([p.name for p in self.app.iterdir()], ['Guigu-Logs.txt'])

    def test_read_only_folder_still_copies_report(self):
        with patch('diagnostics.build_report', return_value='report'), patch('diagnostics.atomic_bytes', side_effect=PermissionError('read only')), \
             patch('diagnostics.copy_to_clipboard'):
            result = d.collect_logs(output_dir=self.app)
        self.assertTrue(result['copied']); self.assertIsNone(result['path'])

    def test_busy_clipboard_still_saves_report(self):
        with patch('diagnostics.build_report', return_value='report'), patch('diagnostics.copy_to_clipboard', side_effect=OSError('busy')):
            result = d.collect_logs(output_dir=self.app)
        self.assertFalse(result['copied']); self.assertTrue(Path(result['path']).is_file())
        self.assertEqual(result['text'], 'report')


if __name__ == '__main__': unittest.main()
