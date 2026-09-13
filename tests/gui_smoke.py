"""Exercise the real Windows Tk UI, capture only its own window, then close."""
import json
import sys
import tkinter as tk
from pathlib import Path
from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run
from extractor import APP, atomic_json


def exercise(app):
    try:
        app.update()
        assert len(app.mods) >= 9
        assert app.provider_label.cget('text') == 'DeepSeek V4.1 Flash'
        assert not hasattr(app, 'engine')
        app.mod_tree.selection_set('2859071194')
        app.select_mod()
        app.update()
        assert app.project['mod']['id'] == '2859071194'
        assert len(app.table.get_children()) > 500
        app.search.set('绝色玉牌')
        app.render()
        app.update()
        visible = app.table.get_children()
        assert visible
        app.table.selection_set(visible[0])
        app.select_unit()
        app.update()
        assert '绝色玉牌' in app.source.get('1.0', 'end')
        ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/gui-smoke.png')
        atomic_json(APP/'projects/gui-smoke.json', {'result':'passed', 'mods':len(app.mods),
                    'project':app.project['mod']['id'], 'filtered_rows':len(visible),
                    'checks':['Windows Tk startup', 'mod discovery', 'project loading', 'search', 'source selection', 'window capture']})
        print('Windows GUI smoke passed')
    finally:
        app.destroy()


tk.Tk.mainloop = exercise
run.gui()
