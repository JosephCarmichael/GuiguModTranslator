"""Real Windows settings dialog and cost gating, with no game or API calls."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import App
from app_config import service_profile
from api_access import ACCESS_FILE
from PIL import ImageGrab


def pump(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.update(); time.sleep(.02)
    assert condition(), 'GUI operation timed out'


with tempfile.TemporaryDirectory(prefix='GuiguKeyGui-') as folder:
    temp = Path(folder)
    resources = temp/'resources'; resources.mkdir()
    data = temp/'data'; data.mkdir()
    (resources/'bundled_service.json').write_text(json.dumps({'api_key': 'sk-or-v1-'+'shared-fixture-'*4}))
    key = 'sk-or-v1-' + 'personal-fixture-' * 4
    with patch('app_config.RESOURCE_DIR', resources), patch('api_access.RESOURCE_DIR', resources), \
         patch('app_config.data_dir', return_value=data), patch('api_access.data_dir', return_value=data), \
         patch('desktop.installed_game', return_value=temp/'game'), \
         patch('desktop.is_friends_build', return_value=True), \
         patch('translation_balance.fetch_key_info', return_value={'limit': 1, 'limit_remaining': .57, 'usage': .43}), \
         patch('game_setup.ensure_setup', return_value={'state': 'ready', 'game': str(temp/'game')}), \
         patch('desktop.discover', return_value=[]), patch.object(App, 'refresh_estimates'):
        app = App()
        try:
            pump(app, lambda: app.setup_ready and not app.busy)
            app.mods = {'expensive': {'id': 'expensive', 'name': 'Large mod'}}
            app.estimates = {'expensive': {'pence': '50', 'complete': True}}
            app.render(); app.list.selection_set('expensive'); app.selected()
            assert app.action.instate(['disabled'])
            assert app.access_note.get() == ''
            dialog = app.api_key_settings(); app.update()
            assert dialog.entry.cget('show')
            dialog.key.set('invalid'); dialog.save_button.invoke(); app.update()
            assert dialog.winfo_exists() and 'beginning with sk-or-' in dialog.message.get()
            assert not (data/ACCESS_FILE).exists()
            dialog.key.set(key); dialog.save_button.invoke(); app.update()
            assert not dialog.winfo_exists() and not dialog.key.get()
            assert app.personal_key and 'no app cost cap' in app.access_note.get()
            assert app.list.set('expensive', 'access') == 'Available'
            assert not app.action.instate(['disabled'])
            assert service_profile()['api_key'] == key
            assert key not in (data/ACCESS_FILE).read_text()
            app.geometry('650x700'); app.update()
            assert app.api_key_button.winfo_ismapped()
            assert app.api_key_button.winfo_rootx() + app.api_key_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            assert app.status_label.winfo_rooty() + app.status_label.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            ImageGrab.grab(window=app.winfo_id()).save(ROOT/'evidence/personal-key-ui.png')
            dialog = app.api_key_settings(); app.update()
            assert not dialog.key.get(), 'Do not expose saved credentials in a reopened dialog'
            dialog.key.set('unsaved'); dialog.close(); app.update()
            assert app.personal_key and service_profile()['api_key'] == key
            dialog = app.api_key_settings(); dialog.shared_button.invoke(); app.update()
            assert not app.personal_key and app.action.instate(['disabled'])
            assert not service_profile()['personal_key']
            app.busy = True
            assert app.api_key_settings() is None
            assert 'Finish or cancel' in app.status.get()
            report = {'result': 'passed', 'checks': ['masked entry', 'invalid input retained for correction',
                      'Windows-encrypted saved key', 'expensive mod immediately unlocked',
                      'personal billing label', 'saved key never prefilled', 'cancel preserves setting',
                      'switch to shared immediately restores cap', 'key change blocked during translation',
                      'minimum-window layout'], 'limits': 'No paid requests or game changes.'}
            (ROOT/'evidence/personal-key-gui.json').write_text(json.dumps(report, indent=2))
            print('Personal OpenRouter key GUI checks passed')
        finally:
            app.estimate_stop.set()
            app.destroy()
