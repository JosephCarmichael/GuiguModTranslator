"""Windows balance header and live confirmation updates, without paid calls."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import App
from translation_balance import BalanceTracker
from PIL import ImageGrab


def pump(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.update(); time.sleep(.02)
    app.update()
    assert condition(), 'GUI operation timed out'


with tempfile.TemporaryDirectory(prefix='GuiguBalanceGui-') as directory:
    temp = Path(directory)
    profile = {'provider': 'OpenRouter', 'api_key': 'sk-or-v1-gui-balance-fixture', 'personal_key': False}
    info = {'limit': 1, 'usage': '.433687782', 'limit_remaining': '.566312218'}
    balance = BalanceTracker(temp)
    with patch('app_config.data_dir', return_value=temp), patch('desktop.installed_game', return_value=temp/'game'), \
         patch('app_config.service_profile', return_value=profile), patch('desktop.is_friends_build', return_value=True), \
         patch('game_setup.ensure_setup', return_value={'state': 'ready', 'game': str(temp/'game')}), \
         patch('desktop.discover', return_value=[]), patch.object(App, 'refresh_estimates'), \
         patch('translation_balance.tracker', return_value=balance), \
         patch('translation_balance.fetch_key_info', return_value=info):
        app = App()
        try:
            pump(app, lambda: app.setup_ready and not app.busy and app.balance_label.get() == 'Balance: ~41.92p')
            assert app.access_note.get() == ''
            assert '$0.5663' in app.balance_detail.get()
            app.geometry('650x770'); app.update()
            ImageGrab.grab(window=app.winfo_id()).save(ROOT/'evidence/balance-header-ui.png')
            balance.record_response(profile, {'id': 'confirmed-batch', 'usage': {'cost': '.01'}})
            pump(app, lambda: app.balance_label.get() == 'Balance: ~41.18p')
            after = app.balance_label.get()
            balance.record_response(profile, {'id': 'confirmed-batch', 'usage': {'cost': '.01'}})
            app.update_balance_display()
            assert app.balance_label.get() == after
            balance.refresh(profile)  # Simulated delayed server total must not refund the charge.
            app.update_balance_display()
            assert app.balance_label.get() == after
            info.update(usage='.443687782', limit_remaining='.556312218')
            balance.refresh(profile); app.update_balance_display()
            assert app.balance_label.get() == after and not balance.snapshot(profile)['estimated']
            profile['api_key'] = 'sk-or-v1-another-key'
            app.refresh_access()
            assert app.balance_label.get() == 'Balance: checking…', 'Old key balance must not carry across'
            report = {'result': 'passed', 'checks': ['top-left balance in GBP with USD source',
                      'old shared-key banner removed', 'confirmed cost lowers displayed balance',
                      'duplicate response ignored', 'delayed refresh cannot restore spent funds',
                      'authoritative refresh does not double subtract', 'key change clears old balance'],
                      'limits': 'Mock balance endpoint and confirmed charge; no paid calls.'}
            (ROOT/'evidence/balance-gui.json').write_text(json.dumps(report, indent=2))
            print('Windows balance header checks passed')
        finally:
            app.estimate_stop.set(); app.destroy()
