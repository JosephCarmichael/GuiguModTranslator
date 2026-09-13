"""Exercise friends cost gating in Windows Tk without paid requests or installs."""
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import App
from destinies import PROJECT_ID
from extractor import APP, atomic_json
from PIL import ImageGrab


def wait_for(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert condition(), 'GUI operation timed out'


mods = [{'id': 'small', 'name': 'Small mod', 'path': '.'},
        {'id': 'large', 'name': 'Large mod', 'path': '.'}]
def estimate(mod, *_):
    return {'pence': {'small': '0.49', 'large': '3', PROJECT_ID: '10'}[mod['id']], 'complete': True}

with tempfile.TemporaryDirectory() as temp, patch('desktop.APP', Path(temp)), \
     patch('desktop.is_friends_build', return_value=True), patch('desktop.discover', return_value=mods), \
     patch('desktop.estimate_mod', side_effect=estimate):
    app = App()
    try:
        wait_for(app, lambda: len(app.estimates) == 3 and not app.busy)
        assert app.list.set('small', 'cost') == '~0.490p'
        app.list.selection_set('large'); app.selected()
        assert app.action.instate(['disabled'])
        assert 'Over 0.5p' in app.list.set('large', 'access')
        with patch('desktop.run_job') as job:
            app.translate()
            job.assert_not_called()
        app.list.selection_set('small'); app.selected()
        assert not app.action.instate(['disabled'])
        app.list.selection_set(PROJECT_ID); app.selected()
        assert app.list.set(PROJECT_ID, 'cost') == '~10.000p'
        assert app.list.set(PROJECT_ID, 'access') == 'Always available'
        assert not app.action.instate(['disabled'])
        app.list.selection_set('large'); app.selected()
        result = {'state': 'success', 'installation': {'count': 1}, 'folder': temp}
        with patch('desktop.run_job', return_value=result) as job:
            app.translate_destinies()
            wait_for(app, lambda: not app.busy)
            assert job.call_args.args[0]['id'] == PROJECT_ID
        app.list.selection_set('large'); app.selected()
        app.geometry('650x700'); app.update()
        assert app.translate_destiny_button.winfo_ismapped()
        assert app.status_label.winfo_rooty() + app.status_label.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/friends-cost-ui.png')
        atomic_json(APP/'projects/friends-cost-gui-check.json', {'result': 'passed',
            'checks': ['cost beside each mod', 'large full mod disabled', 'small full mod enabled',
                       'large destiny project exempt', 'dedicated destiny action from blocked mod',
                       'no paid requests or installed file changes', 'window layout']})
        print('Friends cost UI checks passed')
    finally:
        app.estimate_stop.set()
        app.destroy()
