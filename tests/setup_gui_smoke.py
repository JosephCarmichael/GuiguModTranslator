"""Exercise startup progress, failure and one-click retry in real Windows Tk."""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import App
from app_config import RESOURCE_DIR
from PIL import ImageGrab

with tempfile.TemporaryDirectory() as directory:
    game = Path(directory); entered = threading.Event(); release = threading.Event()
    def first_setup(game, progress, stop):
        progress(75, 'Building the game’s mod interfaces…'); entered.set()
        while not release.wait(.02):
            if stop(): raise InterruptedError('Setup stopped.')
        raise ValueError('First launch interrupted. Click Retry setup.')
    def pump(app, until, seconds=15):
        end = time.monotonic() + seconds
        while not until() and time.monotonic() < end:
            app.update(); time.sleep(.02)
        app.update()
        assert until(), 'GUI operation timed out'
    with patch('desktop.installed_game', return_value=game), patch('game_setup.ensure_setup', side_effect=first_setup), \
         patch('desktop.discover', return_value=[]), patch.object(App, 'refresh_estimates'):
        app = App()
        try:
            pump(app, lambda: entered.is_set() and '75%' in app.status.get())
            assert app.setting_up and app.busy and not app.setup_ready
            assert str(app.bar.cget('mode')) == 'determinate'
            assert app.bar['value'] == 75
            assert app.action.cget('text') == 'Cancel setup'
            assert app.bar.winfo_ismapped()
            app.geometry('650x700'); app.update()
            for widget in (app.bar, app.action, app.status_label, app.play_button):
                assert widget.winfo_rooty() + widget.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            ImageGrab.grab(window=app.winfo_id()).save(RESOURCE_DIR/'evidence/setup-progress-ui.png')
            release.set(); pump(app, lambda: not app.busy)
            assert not app.setup_ready and app.setup_retry.winfo_ismapped()
            assert 'interrupted' in app.status.get()
            with patch('game_setup.ensure_setup', return_value={'state':'ready', 'game':str(game/'repaired')}):
                app.setup_retry.invoke(); pump(app, lambda: app.setup_ready and not app.busy)
            assert app.game == game/'repaired'
            assert not app.setup_retry.winfo_ismapped()
            assert str(app.bar.cget('mode')) == 'indeterminate'
            assert not app.bar.winfo_ismapped()
            report = {'result':'passed','checks':['automatic setup on startup','determinate loading bar',
                      'visible progress and controls','failed setup remains blocked','one-click retry',
                      'repaired game path adopted','normal UI after setup']}
            (RESOURCE_DIR/'evidence/setup-gui-check.json').write_text(json.dumps(report,indent=2))
            print('Windows setup GUI checks passed')
        finally:
            release.set(); app.destroy()
