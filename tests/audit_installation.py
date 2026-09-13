"""Read-only validation against the actual installed mods after extraction."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import APP, CJK, discover, read_json, decode, mod_json, atomic_json


def leaves(node):
    if isinstance(node, dict):
        for value in node.values(): yield from leaves(value)
    elif isinstance(node, list):
        for value in node: yield from leaves(value)
    elif isinstance(node, str):
        try: nested = json.loads(node)
        except ValueError: nested = None
        if isinstance(nested, (dict, list)):
            yield from leaves(nested)
        elif CJK.search(node):
            yield node


def main():
    results = []
    for mod in discover():
        p = read_json(APP/'projects'/mod['id']/'project.json')
        sources = {u['source'] for u in p['units']}
        tested, missing, changed = 0, [], []
        for f in p['coverage']['files']:
            if 'sha256' not in f: continue
            root = Path(mod['path'])
            path = (root if root.is_dir() else root.parent)/f['file']
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != f['sha256']:
                changed.append(f['file'])
            if path.suffix != '.json' and path.name not in ('ModExportData.cache','ModData.cache','ModProject.cache'):
                continue
            if f['status'] != 'scanned': continue
            node = mod_json(decode(raw))
            values = list(leaves(node))
            tested += len(values)
            missing.extend({'file':f['file'], 'source':s} for s in values if s not in sources)
        results.append({'mod':mod['id'], 'name':mod['name'], 'strings':len(sources),
                        'existing_translations':sum(bool(u['translation']) for u in p['units']),
                        'json_chinese_values_checked':tested, 'missing_values':missing,
                        'files_changed_since_scan':changed, 'coverage':p['coverage']['counts']})
    atomic_json(APP/'projects/installation-audit.json', results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    assert all(not r['missing_values'] and not r['files_changed_since_scan'] for r in results)


if __name__ == '__main__': main()
