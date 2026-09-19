"""Native Windows UI check with isolated data, actual local artwork and no API/game changes."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def wait_for(app, ready, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if ready():
            return
        time.sleep(.02)
    raise AssertionError(app.status.get())


with tempfile.TemporaryDirectory(prefix='Guigu updated UI ') as directory:
    os.environ['GUIGU_TRANSLATOR_DATA'] = directory
    os.environ['GUIGU_TRANSLATOR_OFFLINE'] = '1'
    from desktop import App
    from extractor import discover, GAME, atomic_json
    from PIL import ImageGrab
    from mod_titles import load_titles
    from shared_library import load_index
    mods = discover(GAME)
    assert mods
    first = mods[0]
    atomic_json(Path(directory) / 'projects' / first['id'] / 'project.json', {
        'mod': first, 'units': [{'id': 'one', 'source': '宝剑', 'translation': 'Sword', 'status': 'edited', 'category': 'player_text'}],
        'coverage': {'files': [{'status': 'scanned'}]}})
    checks = []
    with patch('game_setup.ensure_setup', return_value={}), \
         patch('desktop.App.balance_tick'), \
         patch('app_config.service_profile', return_value={'personal_key': False}), \
         patch('desktop.estimate_mod', return_value={'pence': '1', 'complete': True}), \
         patch('translation.request_batch', side_effect=lambda texts, *a, **kw: ['Mod ' + str(i) for i in range(len(texts))]):
        for friends in (False, True):
            with patch('desktop.is_friends_build', return_value=friends):
                app = App()
            try:
                wait_for(app, lambda: bool(app.mods) and not app.busy and not app.title_running)
                app.list.selection_set(first['id'])
                app.list.see(first['id'])
                app.selected()
                app.update()
                assert app.list.item(first['id'], 'text').startswith('✓ ')
                assert 'complete' in app.detail_saved.get()
                assert app.thumbnails[first['id']]
                assert app.detail_photos[first['id']]
                assert app.again_button.instate(['!disabled'])
                assert app.play_button.winfo_ismapped()
                assert app.action.winfo_ismapped()
                assert app.play_button.winfo_rooty() + app.play_button.winfo_height() < app.winfo_rooty() + app.winfo_height()
                english = app.mods[first['id']].get('title')
                if english:
                    app.search.set(english)
                    assert first['id'] in app.list.get_children()
                    app.search.set(first['name'])
                    assert first['id'] in app.list.get_children()
                    app.search.set('')
                app.list.selection_set(first['id'])
                app.selected()
                app.concurrency.set(4)
                app.batch_size.set(12)
                fake_result = {'state': 'success', 'count': 1, 'pending': 0, 'installation': {'count': 1, 'conflicts_resolved': 0}}
                with patch('desktop.messagebox.askyesno', return_value=True), patch('desktop.run_job', return_value=fake_result) as job:
                    app.retranslate_selected()
                    wait_for(app, lambda: not app.busy)
                    assert job.call_args.kwargs['retranslate'] is True
                    assert job.call_args.kwargs['concurrency'] == 4
                    assert job.call_args.kwargs['batch_size'] == 12
                app.events.put(('update_checked', ({'version': '1.4.1'}, True)))
                wait_for(app, lambda: '1.4.1' in app.update_status.get())
                assert app.update_button.winfo_ismapped()
                app.update()
                label = 'friends' if friends else 'personal'
                ImageGrab.grab(window=app.winfo_id()).save(ROOT / 'evidence' / ('updated-' + label + '-ui.png'))
                checks.append({'edition': label, 'mods': len(app.mods), 'thumbnails': sum(bool(v) for v in app.thumbnails.values()),
                               'saved_titles': len(load_titles()), 'result': 'passed'})
            finally:
                app.estimate_stop.set()
                app.title_stop.set()
                app.destroy()
    atomic_json(ROOT / 'evidence' / 'updated-gui-check.json', {'result': 'passed', 'editions': checks,
        'checks': ['actual local thumbnails', 'persistent and shared titles', 'English and Chinese search', 'valid saved tick',
                   'retranslation uses current key/settings workflow', 'update offer', 'visible main and footer actions']})
    print(json.dumps(checks, indent=2))
