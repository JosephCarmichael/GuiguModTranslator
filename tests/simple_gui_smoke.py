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
    assert all(str(n) in tuple(map(str, app.parallel.cget('values'))) for n in (16, 32, 64, 128))
    with patch('desktop.save_preferences') as saved:
        app.concurrency.set(32)
        app.change_concurrency()
        saved.assert_called_once_with(concurrency=32)
    ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/simple-preview.png')
    fake={'state':'success','count':3,'pending':0,'installation':{'count':3},'folder':str(APP/'projects/2859071194')}
    with patch('desktop.run_job',return_value=fake) as job:
        app.translate()
        assert str(app.parallel.cget('state')) == 'disabled'
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:
            app.update();time.sleep(0.02)
        assert job.call_args.kwargs['concurrency'] == 32
    assert app.status.get().startswith('Installed 3')
    assert str(app.parallel.cget('state')) == 'readonly'
    ImageGrab.grab(window=app.winfo_id()).save(APP/'projects/simple-success-test.png')
    atomic_json(APP/'projects/simple-gui-check.json',{'result':'passed','mods':len(app.mods),'checks':['mod discovery','selection','parallel request options','saved request limit','selected limit forwarded to job','limit locked during job','simulated success display']})
    print('Simple window checks passed')
finally:
    app.destroy()
