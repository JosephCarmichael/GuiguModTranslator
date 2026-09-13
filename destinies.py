"""Find character-creation text in mod tables and the runtime's loaded inventory."""
from datetime import datetime, timezone
from pathlib import Path

from extractor import (CJK, Scanner, atomic_json, decode, discover, files_in,
                       mod_json, read_json, save_project, validate_translation)

PROJECT_ID = 'character-creation-destinies'
FIELDS = ('name', 'tips', 'introduceText')


def destiny_mod(game):
    return {'id': PROJECT_ID, 'name': 'Character creation destinies',
            'path': str(Path(game).resolve()), 'origin': 'Destiny scan'}


def _rows(value, table='', location='$'):
    if isinstance(value, dict):
        if 'id' in value and table.lower() in ('rolecreatefeature', 'localtext'):
            yield table.lower(), value, location
        for key, child in value.items():
            yield from _rows(child, key if key.lower() in ('rolecreatefeature', 'localtext') else table,
                             location + '/' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _rows(child, table, location + '/' + str(index))
    elif isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try:
            nested = mod_json(value)
        except ValueError:
            return
        yield from _rows(nested, table, location + '/@json')


def scan_destinies(game, folder, progress=None, stop=None, mods=None):
    """A scan costs no translation requests. Preserve edits and installed wording."""
    progress, stop = progress or (lambda _: None), stop or (lambda: False)
    game, folder = Path(game).resolve(), Path(folder)
    scanner = Scanner(destiny_mod(game))
    rows, local, files, gaps = [], {}, [], []
    for mod in discover(game) if mods is None else mods:
        if mod['id'] == PROJECT_ID or Path(mod['path']).suffix.lower() == '.dll':
            continue
        progress('Checking destiny tables in ' + mod['name'] + '…')
        root = Path(mod['path'])
        for path in files_in(root):
            if stop():
                raise InterruptedError('Destiny scan cancelled; saved progress was kept.')
            if path.suffix.lower() not in ('.cache', '.json'):
                continue
            if path.suffix.lower() == '.json' and path.stem.lower() not in ('rolecreatefeature', 'localtext'):
                continue
            file = str(path)
            try:
                for table, row, location in _rows(mod_json(decode(path.read_bytes())), path.stem):
                    if table == 'localtext' and row.get('key'):
                        local.setdefault((mod['id'], str(row['key'])), []).append(row)
                    elif table == 'rolecreatefeature' and str(row.get('type')) == '1':
                        rows.append((mod['id'], row, file, location))
                files.append({'file': file, 'status': 'scanned'})
            except (OSError, ValueError, RecursionError) as error:
                files.append({'file': file, 'status': 'unreadable', 'reason': str(error)})

    fields, native_english = [], {}

    def add_field(ident, field, source, file, location, key='', english=''):
        fields.append({'destiny_id': str(ident), 'field': field, 'source': source,
                       'file': file, 'location': location, 'key': key})
        scanner.add(source, file, location, field, 'player_text', ident, key)
        if english and not CJK.search(english) and not validate_translation(source, english):
            native_english.setdefault(source, set()).add(english)

    for mod_id, row, file, location in rows:
        for field in FIELDS:
            value = str(row.get(field) or '')
            if not value or value == '0':
                continue
            if CJK.search(value):
                add_field(row['id'], field, value, file, location + '/' + field)
                continue
            candidates = local.get((mod_id, value), [])
            if not candidates:
                gaps.append({'destiny_id': str(row['id']), 'field': field, 'key': value,
                             'file': file, 'reason': 'Localisation key needs the loaded game inventory'})
            for candidate in candidates:
                source = candidate.get('ch') or candidate.get('tc') or candidate.get('en') or ''
                add_field(row['id'], field, source, file, location + '/' + field, value, candidate.get('en', ''))

    runtime_file = game / 'UserData/GuiguModTranslator/destiny-inventory.json'
    runtime = None
    runtime_warnings = []
    status_file = runtime_file.with_name('runtime-status.json')
    status = read_json(status_file) if status_file.exists() else {}
    if any(str(error).startswith('Destiny inventory:') for error in status.get('errors', [])):
        runtime_warnings.append('The game reported a destiny detector error. Update the translator and restart the game before scanning again.')
    if runtime_file.exists():
        candidate = read_json(runtime_file)
        if candidate.get('format') != 'guigu-destinies-v1':
            raise ValueError('Unknown destiny inventory format. Update the loader and restart the game.')
        if status.get('process_id') and status['process_id'] != candidate.get('process_id'):
            runtime_warnings.append('The destiny inventory belongs to an older game session; only downloaded tables were scanned. Wait for the current detector to finish, then scan again.')
        else:
            runtime = candidate
    if runtime is not None:
        resolved = set()
        for entry in runtime.get('fields', []):
            if entry.get('unresolved'):
                gaps.append(dict(entry, reason='Loaded localisation key has no text'))
                continue
            resolved.add((str(entry['destiny_id']), entry['field'], entry.get('key', '')))
            add_field(entry['destiny_id'], entry['field'], entry['source'], str(runtime_file),
                      '$/fields/' + str(entry['destiny_id']) + '/' + entry['field'], entry.get('key', ''))
        gaps = [g for g in gaps if (g['destiny_id'], g['field'], g.get('key', '')) not in resolved]
        for index, source in enumerate(runtime.get('observed_untranslated', [])):
            add_field('observed', 'tooltip', source, str(runtime_file), '$/observed_untranslated/' + str(index))

    # Match the runtime's installation priority; ignore dictionaries whose mod moved.
    from installer import paths, read_store
    installed = read_store(paths(game)[1])['mods']
    entries = {}
    for ident, mod in sorted(installed.items(), key=lambda pair: (
            pair[1].get('install_order', 0), pair[1].get('installed_at') or '', pair[0]), reverse=True):
        if not Path(mod['source_path']).exists():
            continue
        for source, target in mod['entries'].items():
            if target and target.strip():
                entries.setdefault(source, target)
    old_file = folder / 'project.json'
    old = read_json(old_file) if old_file.exists() else None
    previous = {u['source']: u for u in old['units']} if old else {}
    for unit in scanner.units.values():
        source = unit['source']
        saved = previous.get(source)
        target = entries.get(source, '')
        if not target and len(native_english.get(source, ())) == 1:
            target = next(iter(native_english[source]))
        if target and not CJK.search(target) and not validate_translation(source, target):
            unit.update(translation=target, status='existing')
        if saved and saved.get('translation') and not CJK.search(saved['translation']) and not validate_translation(source, saved['translation']):
            for key in ('translation', 'status', 'engine', 'model'):
                if key in saved:
                    unit[key] = saved[key]

    project = {'format': 'guigu-mod-text-v1', 'mod': destiny_mod(game),
               'extracted_at': datetime.now(timezone.utc).isoformat(), 'units': list(scanner.units.values()),
               'destiny_fields': fields,
               'coverage': {'files': files, 'counts': {s: sum(f['status'] == s for f in files) for s in ('scanned', 'unreadable')},
                            'complete_player_text_coverage': False, 'destiny_gaps': gaps,
                            'runtime_inventory': {k: runtime.get(k) for k in ('process_id', 'captured_at_utc', 'destiny_count')} if runtime else None,
                            'runtime_warnings': runtime_warnings,
                            'limitations': ['Downloaded tables may include inactive mods. The runtime inventory reflects its last game session.',
                                            'Restart the game and open character creation to refresh all loaded destinies and capture dynamic hover text.']}}
    if old:
        atomic_json(folder / 'project.previous.json', old)
        current = set(scanner.units)
        project['retired_units'] = old.get('retired_units', []) + [u for u in old['units'] if u['id'] not in current and u.get('translation')]
    save_project(project, folder)
    return project


def destiny_report(project):
    units = {u['source']: u for u in project['units']}
    missing = []
    for field in project.get('destiny_fields', []):
        unit = units.get(field['source'])
        if unit and (not unit['translation'] or unit['status'] == 'needs_review' or
                     CJK.search(unit['translation']) or validate_translation(unit['source'], unit['translation'])):
            missing.append(field)
    return {'missing_texts': len({f['source'] for f in missing}), 'missing_fields': missing,
            'unresolved_fields': project['coverage'].get('destiny_gaps', []),
            'runtime_inventory': project['coverage'].get('runtime_inventory'),
            'runtime_warnings': project['coverage'].get('runtime_warnings', []),
            'limitations': project['coverage'].get('limitations', [])}
