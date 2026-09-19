"""Opt-in check against the real installed game and saved Personal data."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_config import RESOURCE_DIR
from desktop import App
from mod_titles import needs_title
from PIL import ImageGrab

with patch('translation.request_batch', side_effect=AssertionError('Saved titles should be reused')) as request:
    app = App()
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            app.update()
            if app.setup_ready and app.mods and not app.busy and not app.scanning_mods:
                break
            time.sleep(0.03)
        assert app.setup_ready, app.status.get()
        assert not app.friends
        assert len(app.mods) >= 17
        assert not any(needs_title(mod, app.titles) for mod in app.mods.values())
        assert not app.title_running
        request.assert_not_called()
        app.list.selection_set(next(iter(app.mods)))
        app.selected()
        app.update()
        assert app.action.instate(['!disabled'])
        ImageGrab.grab(window=app.winfo_id()).save(RESOURCE_DIR / 'evidence/personal-startup-live.png')
        result = {'result':'passed', 'edition':'personal', 'game':str(app.game),
                  'setup_ready':app.setup_ready, 'rows':len(app.list.get_children()),
                  'saved_titles':len(app.titles), 'title_requests_on_reopen':request.call_count,
                  'translate_button_enabled':app.action.instate(['!disabled'])}
        (RESOURCE_DIR/'evidence/personal-startup-live.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
    finally:
        app.estimate_stop.set()
        app.title_stop.set()
        app.destroy()
