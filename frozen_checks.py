"""Dependency and round-trip check runnable from a copied executable."""
import json
import sys
import tempfile
from pathlib import Path

def check(report_path, live=False):
    report = {'frozen':bool(getattr(sys, 'frozen', False)), 'checks':[]}
    try:
        import tkinter as tk
        import yaml
        import openpyxl
        import dnfile
        import UnityPy
        import texture2ddecoder
        from UnityPy.helpers.Tpk import get_typetree_node
        from UnityPy.helpers.UnityVersion import UnityVersion
        from extractor import extract, read_json, MAGIC, MOD_KEY
        from translation import translate
        from app_config import service_profile
        from app_config import RESOURCE_DIR
        import hashlib
        from installer import LOADER
        runtime = RESOURCE_DIR / 'runtime'
        manifest = json.loads((runtime / 'manifest.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((runtime / LOADER).read_bytes()).hexdigest() == manifest['sha256']
        dll = dnfile.dnPE(str(runtime / LOADER))
        assert str(dll.net.mdtables.Assembly.rows[0].Name) == 'GuiguModTranslation'
        dll.close()
        report['checks'].append('Bundled in-game loader and integrity manifest')
        root = tk.Tk(); root.withdraw(); root.update(); root.destroy()
        report['checks'].append('Bundled Python and Tk GUI')
        node = get_typetree_node(49, UnityVersion.from_str('2020.3.9f1'))
        assert node
        report['checks'].append('Unity reader, native codecs and embedded type data')
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory); mod = temp/'mod'; mod.mkdir()
            data = json.dumps({'items':{'LocalText':[{'id':1,'key':'item1','ch':'<r>恢复灵力</r> {0}'}]}},ensure_ascii=False).encode()
            (mod/'ModExportData.cache').write_bytes(MAGIC+bytes((v+MOD_KEY[i%len(MOD_KEY)])&255 for i,v in enumerate(data)))
            (mod/'text.yml').write_text('text: 宝物说明',encoding='utf-8')
            book=openpyxl.Workbook();book.active['D5']='宝剑';book.save(mod/'text.xlsx');book.close()
            p=extract({'id':'portable-test','name':'Portable test','path':str(mod)},temp/'output')
            assert {u['source'] for u in p['units']}=={'<r>恢复灵力</r> {0}','宝物说明','宝剑'}
            assert not p['coverage']['counts'].get('unreadable')
            report['checks'].append('Encoded mod, YAML, Excel, JSON and CSV export')
            profile=service_profile()
            report['provider'],report['model']=profile['provider'],profile['model']
            report['checks'].append('Bundled translation access found (key not logged)')
            if live:
                p['units']=[u for u in p['units'] if u['source'].startswith('<r>')]
                result=translate(p,temp/'output')
                assert result['translated']==1 and result['failed']==0
                report['translation']=p['units'][0]['translation']
                report['checks'].append('Live DeepSeek translation with formatting preserved')
        report['result']='passed'
    except Exception as exc:
        report['result']='failed'
        report['error']=str(exc)
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['result']!='passed':
        raise SystemExit(1)
