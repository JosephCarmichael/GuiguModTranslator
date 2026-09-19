"""Windows Tk check: automatic mod titles and the full-translation tick.

Redirects the app data folder to a temporary folder, so saved translation
projects and the title cache in this repository are never touched, and puts a
stand-in provider in place, so the check makes no paid request.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(tempfile.mkdtemp(prefix='Guigu title check '))
os.environ['GUIGU_TRANSLATOR_DATA'] = str(DATA)

from app_config import RESOURCE_DIR
from extractor import APP, CJK, atomic_json
from mod_titles import display_name, load_titles
from PIL import ImageGrab
from saved_translations import saved_status, tick

FIXTURE_ID = 'title-check-fixture'


def fake_batch(texts, profile, target, stop, glossary=None, gate=None):
    """Stand-in provider: this check never spends credit."""
    return ['English title ' + str(index + 1) for index in range(len(texts))]


def wait_for(app, ready, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if ready():
            return True
        time.sleep(0.02)
    return ready()


def exercise(app):
    assert wait_for(app, lambda: bool(app.mods) and not app.busy), app.status.get()
    chinese = [mod for mod in app.mods.values() if CJK.search(str(mod.get('name', '')))]
    assert len(chinese) >= 2, app.status.get()

    def titled():
        app.render()
        return all(str(app.mods[mod['id']].get('title', '')).startswith('English title') for mod in chinese)
    assert wait_for(app, titled), os.environ.get('GUIGU_TITLES')
    row = app.list.item(chinese[0]['id'], 'text')
    # The English title and the original Chinese name share one row.
    assert row.startswith('English title'), row
    assert '(' + chinese[0]['name'] + ')' in row, row
    assert app.list.item(chinese[0]['id'], 'text') == display_name(app.mods[chinese[0]['id']], load_titles())
    # The titles were saved for the next launch.
    cache = load_titles()
    assert cache, 'mod-titles.json was not written'
    assert all(cache[mod['id']]['source'] == mod['name'] for mod in chinese), cache

    # A mod with a complete saved translation is ticked.
    folder = APP / 'projects' / FIXTURE_ID
    folder.mkdir(parents=True, exist_ok=True)
    atomic_json(folder / 'project.json', {
        'mod': {'id': FIXTURE_ID, 'name': '检查模组', 'path': str(ROOT)},
        'units': [{'id': 'one', 'source': '宝剑', 'translation': 'Sword', 'status': 'machine',
                   'category': 'player_text', 'occurrences': []}],
        'coverage': {'files': [{'status': 'scanned'}], 'counts': {'scanned': 1}}})
    app.mods[FIXTURE_ID] = {'id': FIXTURE_ID, 'name': '检查模组', 'path': str(ROOT), 'origin': 'Check'}
    app.refresh_saved()
    assert wait_for(app, lambda: (app.saved.get(FIXTURE_ID) or {}).get('complete'))
    app.render()
    app.update()
    assert app.list.item(FIXTURE_ID, 'text').startswith(tick({'complete': True}))
    app.list.selection_set(FIXTURE_ID)
    app.selected()
    app.list.see(FIXTURE_ID)
    app.update()
    assert 'already has a full saved translation' in app.status.get(), app.status.get()
    ImageGrab.grab(window=app.winfo_id()).save(RESOURCE_DIR / 'projects/mod-titles-gui.png')
    atomic_json(RESOURCE_DIR / 'projects/mod-titles-gui-check.json', {
        'result': 'passed', 'mods': len(app.mods), 'data_folder': str(APP),
        'titles': {mod['id']: mod.get('title') for mod in app.mods.values() if mod.get('title')},
        'checks': ['automatic mod titles in the saved cache', 'titles persist to mod-titles.json',
                   'English title with the original Chinese name on one row',
                   'full-translation tick from a saved project',
                   'already translated status text', 'window capture']})
    print('Mod title GUI checks passed')


if __name__ == '__main__':
    from desktop import App
    with patch('game_setup.ensure_setup', return_value={}), \
         patch('translation.request_batch', side_effect=fake_batch):
        app = App()
        try:
            exercise(app)
        finally:
            app.destroy()
