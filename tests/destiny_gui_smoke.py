"""Exercise destiny scanning in the Windows UI without changing installed files."""
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import App
from destinies import PROJECT_ID
from extractor import APP, atomic_json, read_json
from PIL import ImageGrab


def wait(app):
    deadline = time.monotonic() + 60
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert not app.busy, 'UI job timed out'


with tempfile.TemporaryDirectory() as temp, patch('desktop.APP', Path(temp)):
    app = App()
    try:
        app.update()
        time.sleep(.1)
        app.update()
        wait(app)
        assert PROJECT_ID in app.mods
        with patch('installer.install_detector', return_value=True) as detector:
            app.find_destinies()
            wait(app)
            detector.assert_called_once_with(app.game)
        assert app.list.selection() == (PROJECT_ID,)
        assert 'untranslated destiny texts' in app.status.get(), app.status.get()
        assert 'Restart the game' in app.status.get()
        assert not app.action.instate(['disabled'])
        report = read_json(app.folder / 'untranslated-destinies.json')
        assert isinstance(report['missing_texts'], int) and report['missing_texts'] >= 0
        app.geometry('650x650')
        app.update()
        for widget in (app.destiny_button, app.action, app.status_label):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty() + widget.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        ImageGrab.grab(window=app.winfo_id()).save(APP / 'projects/destiny-scan-ui.png')
        atomic_json(APP / 'evidence/destiny-gui-check.json', {
            'result': 'passed', 'missing_texts': report['missing_texts'],
            'checks': ['real Windows Tk scan button', 'real mod and runtime scan',
                       'destiny project selected', 'translate button enabled', 'restart instructions', 'saved report']})
        print('Destiny scan UI checks passed')
    finally:
        app.destroy()
