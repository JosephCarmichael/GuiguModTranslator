"""Native clipboard and actual Collect logs button, including during stuck setup."""
import json
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import App
from app_config import RESOURCE_DIR
from PIL import ImageGrab


def pump(app, until):
    end = time.monotonic()+45
    while not until() and time.monotonic()<end:
        app.update(); time.sleep(.02)
    app.update(); assert until(), 'Log collection did not finish'

with tempfile.TemporaryDirectory(prefix='Guigu Clipboard Test ') as temp, \
     patch.object(App, 'start_setup'), patch('diagnostics.APP_DIR', Path(temp)):
    app = App()
    try:
        app.update()
        app.busy = app.setting_up = True
        app.status.set('50% · Starting Tale of Immortal…')
        app.bar.configure(mode='determinate', value=50)
        app.bar.pack(before=app.action, fill='x')
        app.logs_button.invoke()
        pump(app, lambda: not app.collecting_logs)
        report = (Path(temp)/'Guigu-Logs.txt').read_text(encoding='utf-8-sig')
        assert 'Windows application crashes' in report and 'windows_ansi_code_page' in report
        assert '50% · Starting Tale of Immortal' in report
        assert app.clipboard_get() == report
        assert app.busy and app.setting_up and not app.stop.is_set()
        assert app.status.get() == '50% · Starting Tale of Immortal…'
        assert 'Copied' in app.log_status.get()
        app.geometry('650x650'); app.update()
        assert app.logs_button.winfo_ismapped()
        assert app.logs_button.winfo_rooty() + app.logs_button.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        ImageGrab.grab(window=app.winfo_id()).save(RESOURCE_DIR/'evidence/collect-logs-button.png')
    finally:
        app.destroy()
    # Windows owns the clipboard bytes after the app window is gone.
    reader = tk.Tk(); reader.withdraw()
    try:
        persisted = reader.clipboard_get()
        assert persisted.replace("\r\n", "\n") == report, (len(persisted), len(report), repr(persisted[:60]))
    finally:
        reader.destroy()
    evidence = {'result':'passed','characters':len(report),'checks':['visible Collect logs button at minimum window size',
        'collect during stuck setup without cancelling it','real Windows application events and code page',
        'plain text beside executable','Unicode clipboard equals report','clipboard survives window closing']}
    (RESOURCE_DIR/'evidence/collect-logs-gui-check.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))
