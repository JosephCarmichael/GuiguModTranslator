"""Read-only Tale of Immortal mod text extraction. Never loads a mod DLL."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from app_config import APP_DIR, data_dir, installed_game

APP = data_dir()
GAME = installed_game() or APP_DIR
MAGIC = b'1b8bg-/%ePe]P[-/921CG'
# GameConf.modEncryPassword; EncryptTool.EncryptMult adds repeating UTF-8 bytes.
# Verified against this installation's native implementation and JSON payloads.
MOD_KEY = b',.?<aH.5:.L;_=-A%K/DF4s'
CJK = re.compile('[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
TAGS = re.compile(r'<[^<>\n]+>')
DISPLAY = re.compile(r'^(ch|tc|cn|zh|zh_cn|zh_tw|text|m_text|dialogue|title|name|desc|description|tips|tip|content|message|label|caption|help|intro|introduceText|option|answer|question|notice|story|speech|tooltip|hint|姓名|名称|描述|文本|对话|提示)$', re.I)
STRUCTURAL = re.compile(r'^(id|key|soleID|modNamespace|path|.*Path|.*Icon|icon|sprite|m_Name|m_EditorClassIdentifier|condition|function|trigger|effect|assetBundleName|guid|.*FileName)$', re.I)
MEDIA = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tga', '.dds', '.gif', '.wav', '.mp3', '.ogg', '.webm', '.mp4', '.dat'}
TEXT = {'.txt', '.json', '.csv', '.tsv', '.xml', '.yml', '.yaml', '.html', '.htm', '.lua', '.js', '.cs', '.ini', '.cfg', '.prefab', '.asset', '.unity'}
SKIP_DIRS = {'.git', '.vs', 'obj', 'Library', 'Temp', 'Logs', 'Packages', 'ProjectSettings', '__pycache__'}
TOKENS = re.compile(r'<[^<>\n]+>|\{\{[^{}]*\}\}|\{[^{}\n]+\}|\\[A-Za-z]+\[[^\]]*\]|\\[nrt]|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdfiu]|\[[A-Za-z_][\w.:=-]*\]')


def decode(data: bytes) -> str:
    if data.startswith(MAGIC):
        data = bytes((v - MOD_KEY[i % len(MOD_KEY)]) & 255 for i, v in enumerate(data[len(MAGIC):]))
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    if b'\0' in data[:100]:
        raise ValueError('Binary payload, not decoded text')
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return data.decode(encoding)
        except UnicodeError:
            pass
    raise ValueError('Unsupported text encoding')


def read_json(path):
    return json.loads(decode(Path(path).read_bytes()))


def mod_json(text):
    """The game's JSON reader accepts comments and trailing commas."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Tokenise strings first so URLs, escaped quotes and comment-like prose
        # inside localisation strings survive byte-for-byte.
        token = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/', re.S)
        clean = token.sub(lambda m: m.group() if m.group().startswith('"') else ' ', text)
        clean = re.sub(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])',
                       lambda m: m.group(1) if m.group(1) is not None else m.group(), clean)
        return json.loads(clean)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def discover(game=GAME, extra_roots=()):
    game = Path(game)
    roots = [game.parent.parent / 'workshop' / 'content' / '1468810', game / 'ModExportData', game / 'Mods']
    roots.extend(Path(p) for p in extra_roots)
    mods, seen = [], set()
    for root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            if folder.is_file() and folder.suffix.lower() != '.dll':
                continue
            if not folder.is_dir() and not folder.is_file():
                continue
            canonical = str(folder.resolve())
            if canonical in seen:
                continue
            seen.add(canonical)
            manifests = [folder / 'ModExportData.cache', folder / 'ModProject' / 'ModProject.cache'] if folder.is_dir() else []
            if folder.is_dir():
                manifests += sorted(folder.glob('debug/*/ModExportData.cache'))
            meta, warning = {}, ''
            for manifest in manifests:
                if not manifest.is_file():
                    continue
                try:
                    value = read_json(manifest)
                    meta = value.get('projectData', value)
                    break
                except Exception as exc:
                    warning = str(exc)
            mod_id = folder.name if root.name == '1468810' else folder.stem + '-' + hashlib.sha256(canonical.encode()).hexdigest()[:8]
            mods.append({'id': mod_id, 'name': TAGS.sub('', str(meta.get('name', folder.stem))).strip(),
                         'path': canonical, 'author': meta.get('author', ''), 'version': meta.get('ver', ''),
                         'namespace': meta.get('soleID', ''), 'origin': 'Workshop' if root.name == '1468810' else 'Local',
                         'metadata_warning': warning})
    return mods


def files_in(root):
    if root.is_file():
        yield root
        return
    def onerror(exc):
        raise exc
    for parent, dirs, files in os.walk(root, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not Path(parent, d).is_symlink())
        for name in sorted(files):
            p = Path(parent, name)
            if not p.is_symlink():
                yield p


class Scanner:
    def __init__(self, mod, progress=None, stop=None):
        self.mod = mod
        self.root = Path(mod['path'])
        self.units = {}
        self.files = []
        self.progress = progress or (lambda _: None)
        self.stop = stop or (lambda: False)
        self.seen = {}
        self.references = {}
        self.existing_translations = {}

    def add(self, source, file, location, field='', category=None, row='', key=''):
        if not isinstance(source, str) or not CJK.search(source):
            return
        if len(source) > 250000:
            raise ValueError('Text value exceeds 250,000 characters; review file separately')
        if category is None:
            category = 'player_text' if DISPLAY.match(str(field)) else 'review'
            if STRUCTURAL.match(str(field)):
                category = 'technical'
        # Exact source identities: preserve whitespace and markup, retain every occurrence.
        ident = hashlib.sha256(source.encode('utf-8')).hexdigest()[:24]
        unit = self.units.setdefault(ident, {'id': ident, 'source': source, 'translation': '', 'status': 'untranslated',
                                            'category': category, 'occurrences': [], 'tokens': TOKENS.findall(source)})
        rank = {'player_text': 0, 'review': 1, 'technical': 2}
        if rank[category] < rank[unit['category']]:
            unit['category'] = category
        occurrence = {'file': file, 'location': location, 'field': str(field), 'row_id': str(row), 'localization_key': str(key)}
        unit['occurrences'].append(occurrence)

    def walk(self, obj, file, location='$', field='', row='', key='', category=None, depth=0):
        if depth > 100:
            raise ValueError('Nested data exceeds 100 levels')
        if isinstance(obj, dict):
            row = obj.get('id', row)
            key = obj.get('key', key)
            source, english = obj.get('ch'), obj.get('en')
            if isinstance(source, str) and isinstance(english, str) and english.strip() and not CJK.search(english):
                if not validate_translation(source, english):
                    self.existing_translations.setdefault(source, set()).add(english)
            for k, v in obj.items():
                # Chinese dictionary keys can be UI labels, but also identifiers.
                self.add(k, file, location + '/@key:' + str(k), category='review')
                loc = location + '/' + str(k).replace('~', '~0').replace('/', '~1')
                self.walk(v, file, loc, str(k), row, key, category, depth + 1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self.walk(v, file, location + '/' + str(i), field, row, key, category, depth + 1)
        elif isinstance(obj, str):
            stripped = obj.lstrip()
            if stripped.startswith(('{', '[')):
                try:
                    nested = json.loads(obj)
                except ValueError:
                    nested = None
                if isinstance(nested, (dict, list)):
                    self.walk(nested, file, location + '/@json', field, row, key, category, depth + 1)
                    return
            self.add(obj, file, location, field, category, row, key)
            if not CJK.search(obj) and obj and DISPLAY.match(field):
                self.references.setdefault(obj, []).append({'file': file, 'location': location, 'row_id': str(row)})

    def text(self, text, file, suffix, prefix='$'):
        if suffix == '.json' or text.lstrip().startswith(('{', '[')):
            try:
                self.walk(mod_json(text), file, prefix)
                return
            except json.JSONDecodeError:
                if suffix == '.json':
                    raise
        if suffix in ('.yaml', '.yml'):
            import yaml
            for i, obj in enumerate(yaml.safe_load_all(text)):
                self.walk(obj, file, prefix + '/doc' + str(i))
            return
        if suffix in ('.csv', '.tsv'):
            for i, row in enumerate(csv.reader(io.StringIO(text), delimiter='\t' if suffix == '.tsv' else ',')):
                for j, cell in enumerate(row):
                    self.add(cell, file, f'{prefix}/row{i+1}/col{j+1}')
            return
        if suffix in ('.cs', '.js', '.lua'):
            # Lexically skip comments; all literals remain review candidates since
            # static extraction cannot prove whether code reaches a UI or logger.
            rx = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|--[^\n]*|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
            for match in rx.finditer(text):
                raw = match.group()
                if raw.startswith(('//', '/*', '--')):
                    continue
                if raw.startswith('@"'):
                    value = raw[2:-1].replace('""', '"')
                else:
                    try:
                        value = json.loads(raw) if raw.startswith('"') else raw[1:-1]
                    except ValueError:
                        value = raw[1:-1]
                self.add(value, file, f'{prefix}/line{text.count(chr(10), 0, match.start())+1}', category='review')
            return
        if suffix in ('.xml', '.html', '.htm'):
            from html.parser import HTMLParser
            scanner = self
            class Parser(HTMLParser):
                def handle_data(self, data):
                    scanner.add(data, file, f'{prefix}/line{self.getpos()[0]}', category='review')
                def handle_starttag(self, tag, attrs):
                    for k, v in attrs:
                        if v:
                            scanner.add(v, file, f'{prefix}/line{self.getpos()[0]}/@{k}', k)
            Parser().feed(text)
            return
        for i, line in enumerate(text.splitlines()):
            # Unity YAML and ordinary config: retain the field value, not indentation.
            match = re.match(r'\s*([\w]+)\s*:\s*(.*)$', line)
            if match:
                field, value = match.groups()
                if value.startswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        pass
                self.add(value, file, f'{prefix}/line{i+1}', field)
            else:
                self.add(line, file, f'{prefix}/line{i+1}', category='review')

    def dll(self, data, file, report):
        import dnfile
        pe = dnfile.dnPE(data=data, clr_lazy_load=True)
        try:
            if not pe.net:
                raise ValueError('Native DLL: no .NET string heap')
            heap = pe.net.user_strings
            if heap:
                offset = 1
                while offset < heap.sizeof():
                    item = heap.get(offset)
                    if not item or item.raw_size <= 0 or item.item_size == 0:
                        break
                    self.add(item.value, file, f'#US/0x{offset:x}', category='review')
                    offset += item.raw_size
            for res in pe.net.resources:
                payload = res.data
                if hasattr(payload, 'entries'):
                    for entry in payload.entries:
                        self.add(entry.value, file, f'resource/{res.name}/{entry.name}', category='review')
                elif isinstance(payload, bytes):
                    try:
                        self.text(decode(payload), file, Path(str(res.name)).suffix.lower(), f'resource/{res.name}')
                    except (UnicodeError, ValueError):
                        report.setdefault('opaque_resources', []).append(str(res.name))
            report['runtime_review'] = 'Literal strings extracted; dynamically generated or obfuscated text requires in-game capture.'
        finally:
            pe.close()

    def spreadsheet(self, data, file):
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        try:
            for sheet in book:
                headers = None
                for row_index, cells in enumerate(sheet, 1):
                    values = [c.value for c in cells]
                    if row_index <= 4 and 'id' in values and any(v in values for v in ('key', 'name', 'ch', 'desc', 'tips')):
                        headers = values
                        continue
                    if headers:
                        record = {str(k): c.value for k, c in zip(headers, cells) if k is not None and c.data_type != 'f'}
                        # Field types are editor schema, not display values.
                        if record.get('id') in ('int', 'string', 'long'):
                            continue
                        self.walk(record, file, f'{sheet.title}/row{row_index}')
                    else:
                        for cell in cells:
                            if isinstance(cell.value, str) and cell.data_type != 'f':
                                self.add(cell.value, file, sheet.title + '/' + cell.coordinate, category='review')
        finally:
            book.close()

    def unity(self, data, file, report):
        import UnityPy
        env = UnityPy.load(data)
        types = Counter()
        errors = []
        for obj in env.objects:
            kind = obj.type.name
            types[kind] += 1
            if kind not in ('TextAsset', 'MonoBehaviour'):
                continue
            loc = f'Unity/{obj.assets_file.name}/{obj.path_id}/{kind}'
            try:
                if kind == 'TextAsset':
                    value = obj.read()
                    payload = value.m_Script
                    if isinstance(payload, str):
                        payload = payload.encode('utf-8', errors='surrogateescape')
                    self.text(decode(payload), file, Path(value.m_Name).suffix.lower(), loc)
                else:
                    tree = obj.read_typetree()
                    self.walk(tree, file, loc)
                    if set(tree).issubset({'m_GameObject', 'm_Enabled', 'm_Script', 'm_Name', 'm_EditorClassIdentifier'}):
                        errors.append(loc + ': no custom fields in type tree; needs runtime review')
            except Exception as exc:
                errors.append(loc + ': ' + str(exc))
        report['object_types'] = dict(types)
        if not types:
            raise ValueError('No Unity objects were readable')
        if errors:
            report['object_errors'] = errors
            report['status'] = 'partial'
        if types['Texture2D'] or types['Sprite']:
            report['image_review'] = 'Texture/sprite content needs visual review or OCR for baked-in lettering.'

    def scan(self):
        base = self.root if self.root.is_dir() else self.root.parent
        for index, path in enumerate(files_in(self.root)):
            if self.stop():
                raise InterruptedError('Extraction cancelled; previous project was preserved')
            rel = path.relative_to(base).as_posix()
            suffix = path.suffix.lower()
            report = {'file': rel, 'status': 'ignored'}
            self.files.append(report)
            if index % 25 == 0:
                self.progress(f'{self.mod["name"]}: {index + 1} files, {len(self.units):,} strings — {rel}')
            if suffix in MEDIA:
                report['status'] = 'media_review'
                report['reason'] = 'Media: visual/OCR or audio review needed; no claim of textual coverage.'
                continue
            if suffix not in TEXT | {'.cache', '.dll', '.ab', '.xlsx', '.bundle', '.resources', ''}:
                continue
            if suffix == '.cache' and path.name not in ('ModExportData.cache', 'ModData.cache', 'ModProject.cache'):
                continue
            try:
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                report['sha256'] = digest
                report['bytes'] = len(data)
                # Duplicate assets occur in source and exported debug trees. Retain
                # occurrence aliases, and copy coverage failures as well as successes.
                if digest in self.seen:
                    old = self.seen[digest]
                    report.update({k: v for k, v in old.items() if k != 'file'})
                    report['duplicate_of'] = old['file']
                    for unit in self.units.values():
                        for occurrence in list(unit['occurrences']):
                            if occurrence['file'] == old['file']:
                                unit['occurrences'].append(dict(occurrence, file=rel))
                    continue
                self.seen[digest] = report
                report['status'] = 'scanned'
                if suffix == '.dll':
                    self.dll(data, rel, report)
                elif suffix in ('.ab', '.bundle') or data.startswith((b'UnityFS', b'UnityRaw', b'UnityWeb')):
                    self.unity(data, rel, report)
                elif suffix == '.xlsx':
                    self.spreadsheet(data, rel)
                elif suffix == '.cache':
                    self.walk(json.loads(decode(data)), rel)
                else:
                    self.text(decode(data), rel, suffix)
            except Exception as exc:
                report['status'] = 'unreadable'
                report['reason'] = f'{type(exc).__name__}: {exc}'
        for unit in self.units.values():
            existing = sorted(self.existing_translations.get(unit['source'], []))
            if len(existing) == 1:
                unit['translation'], unit['status'] = existing[0], 'existing'
            elif existing:
                unit['existing_translation_candidates'] = existing
            keys = {o['localization_key'] for o in unit['occurrences'] if o['localization_key']}
            refs = [r for key in sorted(keys) for r in self.references.get(key, [])]
            if refs:
                unit['referenced_by'] = refs
        return {'format': 'guigu-mod-text-v1', 'mod': self.mod, 'extracted_at': datetime.now(timezone.utc).isoformat(),
                'units': sorted(self.units.values(), key=lambda u: (u['category'], u['id'])),
                'coverage': {'files': self.files, 'counts': dict(Counter(f['status'] for f in self.files)),
                             'categories': dict(Counter(u['category'] for u in self.units.values())),
                             'complete_player_text_coverage': False,
                             'limitations': ['Static extraction cannot prove every string is displayed.',
                                             'Images, audio, generated text, and obfuscated code require separate review.',
                                             'Review candidates include internal strings; technical identifiers must not be blindly patched.']}}


def validate_translation(source, translation):
    if not isinstance(translation, str):
        return 'Translation must be text'
    if translation and TOKENS.findall(source) != TOKENS.findall(translation):
        return 'Formatting tags or placeholders changed (including order)'
    return ''


def save_project(project, folder):
    folder = Path(folder)
    atomic_json(folder / 'project.json', project)
    atomic_json(folder / 'coverage.json', project['coverage'])
    export_csv(project, folder / 'strings.csv')
    atomic_json(folder / 'strings.json', project['units'])
    atomic_json(folder / 'dictionary.json', {u['source']: u['translation'] for u in project['units']
                if u['translation'] and u['category'] != 'technical' and not validate_translation(u['source'], u['translation'])})


def extract(mod, folder, progress=None, stop=None):
    project = Scanner(mod, progress, stop).scan()
    old_path = Path(folder) / 'project.json'
    if old_path.exists():
        old = read_json(old_path)
        old_units = {u['id']: u for u in old['units']}
        for u in project['units']:
            previous = old_units.get(u['id'])
            if previous and previous['source'] == u['source'] and previous['translation']:
                u['translation'], u['status'] = previous['translation'], previous['status']
        current = {u['id'] for u in project['units']}
        project['retired_units'] = old.get('retired_units', []) + [u for u in old['units'] if u['id'] not in current and u['translation']]
        atomic_json(Path(folder) / 'project.previous.json', old)
    save_project(project, folder)
    return project


def export_csv(project, path):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow(['id', 'source', 'translation', 'category', 'status', 'occurrences'])
    for u in project['units']:
        # Quote every cell, and leave exact source intact for machine round trips.
        writer.writerow([u['id'], u['source'], u['translation'], u['category'], u['status'], json.dumps(u['occurrences'], ensure_ascii=False)])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(stream.getvalue(), encoding='utf-8-sig', newline='')
    temp.replace(path)


def import_csv(project, path):
    units = {u['id']: u for u in project['units']}
    changes = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not {'id', 'source', 'translation'}.issubset(reader.fieldnames or []):
            raise ValueError('CSV must have id, source, translation columns')
        for row in reader:
            u = units.get(row['id'])
            if not u or u['source'] != row['source']:
                raise ValueError('CSV source/ID does not match project: ' + row['id'])
            translation = row['translation']
            error = validate_translation(u['source'], translation)
            if error:
                raise ValueError(row['id'] + ': ' + error)
            if row['id'] in changes and changes[row['id']] != translation:
                raise ValueError('Conflicting duplicate CSV row: ' + row['id'])
            changes[row['id']] = translation
    for ident, value in changes.items():
        units[ident]['translation'] = value
        units[ident]['status'] = 'edited' if value else 'untranslated'
    return len(changes)
