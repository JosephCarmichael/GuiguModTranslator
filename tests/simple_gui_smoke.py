import sys
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import App
from extractor import APP, atomic_json
from PIL import ImageGrab

app=App()
try:
    deadline=time.monotonic()+20
    while (not app.mods or app.busy) and time.monotonic()<deadline:
        app.update();time.sleep(0.02)
    assert len(app.mods)>=9
    app.list.selection_set('2859071194');app.selected();app.update()
    assert app.action.cget('text')=='Translate and install'
    ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/simple-preview.png')
    fake={'state':'success','count':3,'pending':0,'installation':{'count':3},'folder':str(APP/'projects/2859071194')}
    with patch('desktop.run_job',return_value=fake):
        app.translate()
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:
            app.update();time.sleep(0.02)
    assert app.status.get().startswith('Installed 3')
    ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/simple-success-test.png')
    atomic_json(APP/'projects/simple-gui-check.json',{'result':'passed','mods':len(app.mods),'checks':['mod discovery','selection','single button','simulated success display']})
    print('Simple window checks passed')
finally:
    app.destroy()
