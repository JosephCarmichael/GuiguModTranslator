"""Exercise bulk price selection, queue progress and cancellation in Windows Tk."""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import App
from PIL import ImageGrab


def pump(app, condition):
    end = time.monotonic() + 10
    while not condition() and time.monotonic() < end:
        app.update(); time.sleep(.02)
    app.update()
    assert condition(), 'GUI operation timed out'


with tempfile.TemporaryDirectory(prefix='GuiguBulkGui-') as directory:
    temp = Path(directory)
    with patch('desktop.APP', temp), patch('app_config.data_dir', return_value=temp), \
         patch('desktop.installed_game', return_value=temp/'game'), \
         patch('desktop.is_friends_build', return_value=True), \
         patch('app_config.service_profile', return_value={'personal_key': True}), \
         patch('game_setup.ensure_setup', return_value={'state': 'ready', 'game': str(temp/'game')}), \
         patch('desktop.discover', return_value=[]), patch.object(App, 'refresh_estimates'):
        app = App()
        release, entered = threading.Event(), threading.Event()
        try:
            pump(app, lambda: app.setup_ready and not app.busy)
            app.mods = {ident: {'id': ident, 'name': name} for ident, name in
                        [('cheap', 'Cheap mod'), ('medium', 'Medium mod'), ('limit', 'At £2'),
                         ('over', 'Over £2'), ('unknown', 'Unknown price')]}
            app.estimates = {ident: {'pence': str(pence), 'complete': True} for ident, pence in
                             [('cheap', 5), ('medium', 180), ('limit', 200), ('over', 201)]}
            app.render()
            assert app.bulk_button.instate(['disabled']), 'Wait for all individual mod estimates'
            app.estimates['unknown'] = {'error': True}
            app.render()
            assert '1 matching' in app.bulk_note.get()
            assert '5p per mod' in app.bulk_price_label.get()
            app.price_slider.set(200); app.update()
            assert '3 matching' in app.bulk_note.get() and '£3.85' in app.bulk_note.get()
            assert '£2.00 per mod' in app.bulk_price_label.get()
            app.search.set('Cheap'); app.update()
            assert len(app.list.get_children()) == 1 and '3 matching' in app.bulk_note.get()
            calls = []
            def job(mod, folder, progress, stop, **kwargs):
                calls.append((mod['id'], kwargs['max_pence']))
                entered.set(); progress('Translating remaining text…')
                while not release.wait(.02):
                    if stop():
                        return {'state': 'cancelled'}
                return {'state': 'success'}
            with patch('mod_workflow.run_job', side_effect=job):
                app.bulk_button.invoke()
                pump(app, lambda: entered.is_set() and '1/3' in app.status.get())
                assert app.bulk_running and app.busy
                assert app.bulk_button.cget('text') == 'Cancel all'
                assert app.price_slider.cget('state') == 'disabled'
                assert str(app.bar.cget('mode')) == 'determinate'
                app.bulk_button.invoke()
                pump(app, lambda: not app.busy)
            assert calls == [('cheap', 200)]
            assert 'cancelled' in app.status.get().lower() and '2 not started' in app.status.get()
            release.set(); calls.clear()
            with patch('mod_workflow.run_job', side_effect=job):
                app.bulk_button.invoke()
                pump(app, lambda: not app.busy)
            assert calls == [('cheap', 200), ('medium', 200), ('limit', 200)]
            assert '3 complete' in app.status.get()
            assert app.price_slider.cget('state') == 'normal'
            app.save_bulk_price()
            assert json.loads((temp/'preferences.json').read_text())['bulk_price_pence'] == 200
            app.search.set(''); app.geometry('650x700'); app.update()
            for widget in (app.bulk_button, app.price_slider, app.action, app.status_label, app.play_button):
                assert widget.winfo_ismapped()
                assert widget.winfo_rooty() + widget.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            ImageGrab.grab(window=app.winfo_id()).save(ROOT/'evidence/translate-all-ui.png')
            with patch('app_config.service_profile', return_value={'personal_key': False}):
                app.refresh_access()
                assert not app.bulk_button.instate(['disabled'])
                assert '1 matching' in app.bulk_note.get()
                assert app.list.set('cheap', 'access') == 'Available'
                assert app.list.set('medium', 'access') == 'Over 5p limit'
            report = {'result': 'passed', 'checks': ['5p default and £2 slider maximum',
                      'per-mod inclusive matching and combined estimate', 'unknown prices excluded',
                      'waits for estimates', 'all mods independent of search', 'cheapest first',
                      'progress and safe cancellation', 'price frozen during queue', 'shared cap respected',
                      'saved slider preference', 'minimum-window layout'], 'limits': 'Fixture mod jobs; no paid requests or game changes.'}
            (ROOT/'evidence/translate-all-gui.json').write_text(json.dumps(report, indent=2))
            print('Translate all Windows GUI checks passed')
        finally:
            release.set(); app.stop.set(); app.estimate_stop.set()
            app.destroy()
