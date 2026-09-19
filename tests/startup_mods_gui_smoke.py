"""Windows startup regression: real mod discovery, no setup changes or API calls."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def wait_for(app, condition):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.update()
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(app.status.get())


with tempfile.TemporaryDirectory() as data:
    os.environ['GUIGU_TRANSLATOR_DATA'] = data
    from desktop import App
    from mod_titles import load_titles
    from PIL import ImageGrab

    release_setup = threading.Event()

    def setup(*args):
        release_setup.wait(30)
        raise ValueError('Fixture: game launch repair required')

    with patch('game_setup.ensure_setup', side_effect=setup), \
         patch('desktop.App.balance_tick'), \
         patch('app_config.service_profile', return_value={'personal_key': False}), \
         patch('translation.request_batch', side_effect=lambda texts, *a, **kw: ['Mod ' + str(i) for i in range(len(texts))]):
        app = App()
        try:
            wait_for(app, lambda: bool(app.mods) and not app.title_running)
            assert app.setting_up and app.busy
            assert len(app.list.get_children()) == len(app.mods)
            assert load_titles()
            release_setup.set()
            wait_for(app, lambda: not app.busy)
            assert not app.setup_ready
            assert 'launch repair required' in app.status.get()
            app.list.selection_set(next(iter(app.mods)))
            app.selected()
            assert 'launch repair required' in app.status.get()
            assert app.action.instate(['disabled'])
            assert app.bulk_button.instate(['disabled'])
            assert app.list.get_children()
            with patch('translation.request_batch') as request:
                app.refresh()
                wait_for(app, lambda: not app.scanning_mods)
                request.assert_not_called()
            # Missing access must be visible and must not hide the mod list.
            Path(data, 'mod-titles.json').unlink()
            app.titles = {}
            with patch('app_config.service_profile', side_effect=ValueError('Fixture: missing key')):
                app.start_titles()
                wait_for(app, lambda: not app.title_running)
            assert 'missing key' in app.title_status.get()
            assert app.list.get_children()
            ImageGrab.grab(window=app.winfo_id()).save(ROOT / 'evidence/startup-mods-review.png')
            print(f'PASS: {len(app.mods)} rows during setup and after failure; saved titles reused; errors visible; install controls disabled.')
        finally:
            release_setup.set()
            app.estimate_stop.set()
            app.title_stop.set()
            app.destroy()
