from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from extractor import APP, GAME, discover, extract, atomic_json, read_json, save_project, export_csv, import_csv, validate_translation
from translation import DEEPSEEK_LABEL


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title('Guigu Mod Translator — Chinese text extraction')
            self.geometry('1380x870')
            self.minsize(980, 650)
            self.mods, self.project, self.folder, self.current = {}, None, None, None
            self.queue = queue.Queue()
            self.stop = threading.Event()
            self.busy = False
            self.protocol('WM_DELETE_WINDOW', self.close)
            self.game = tk.StringVar(value=str(GAME))
            self.search = tk.StringVar()
            self.category = tk.StringVar(value='All extracted text')
            self.include_review = tk.BooleanVar(value=False)
            self.status = tk.StringVar(value='Select a mod, then Extract Chinese text.')
            top = ttk.Frame(self, padding=10)
            top.pack(fill='x')
            ttk.Label(top, text='Game folder').grid(row=0, column=0, sticky='w')
            ttk.Entry(top, textvariable=self.game).grid(row=0, column=1, sticky='ew', padx=8)
            ttk.Button(top, text='Browse', command=self.browse_game).grid(row=0, column=2)
            ttk.Button(top, text='Refresh mods', command=self.refresh).grid(row=0, column=3, padx=6)
            top.columnconfigure(1, weight=1)
            panes = ttk.Panedwindow(self, orient='horizontal')
            panes.pack(fill='both', expand=True, padx=10)
            left, right = ttk.Frame(panes), ttk.Frame(panes)
            panes.add(left, weight=1)
            panes.add(right, weight=4)
            ttk.Label(left, text='Downloaded and local mods').pack(anchor='w', pady=4)
            self.mod_tree = ttk.Treeview(left, columns=('origin',), show='tree headings', height=17, selectmode='browse')
            self.mod_tree.heading('#0', text='Mod')
            self.mod_tree.heading('origin', text='Source')
            self.mod_tree.column('#0', width=255)
            self.mod_tree.column('origin', width=75)
            self.mod_tree.pack(fill='both', expand=True)
            self.mod_tree.bind('<<TreeviewSelect>>', self.select_mod)
            ttk.Button(left, text='Add a mod folder…', command=self.add_mod).pack(fill='x', pady=5)
            self.extract_button = ttk.Button(left, text='Extract Chinese text', command=self.extract_selected)
            self.extract_button.pack(fill='x', pady=5)
            ttk.Button(left, text='Open project folder', command=self.open_folder).pack(fill='x', pady=5)
            ttk.Button(left, text='View coverage report', command=self.coverage).pack(fill='x', pady=5)
            filters = ttk.Frame(right)
            filters.pack(fill='x', pady=4)
            ttk.Entry(filters, textvariable=self.search).pack(side='left', fill='x', expand=True)
            ttk.Combobox(filters, textvariable=self.category, state='readonly', width=20,
                         values=['All extracted text', 'Player text', 'Review candidates', 'Technical', 'Untranslated']).pack(side='left', padx=6)
            self.search.trace_add('write', lambda *_: self.filter_debounce())
            self.category.trace_add('write', lambda *_: self.filter_debounce())
            self.filter_job = None
            table_frame = ttk.Frame(right)
            table_frame.pack(fill='both', expand=True)
            self.table = ttk.Treeview(table_frame, columns=('category', 'source', 'translation'), show='headings', selectmode='browse')
            for col, label, width in [('category', 'Category', 100), ('source', 'Chinese source', 360), ('translation', 'Translation', 300)]:
                self.table.heading(col, text=label)
                self.table.column(col, width=width)
            scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
            self.table.configure(yscrollcommand=scroll.set)
            self.table.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            self.table.bind('<<TreeviewSelect>>', self.select_unit)
            ttk.Label(right, text='Selected source and locations').pack(anchor='w', pady=(7, 0))
            self.source = tk.Text(right, height=6, wrap='word', state='disabled')
            self.source.pack(fill='x')
            ttk.Label(right, text='Translation (keep formatting tags and placeholders)').pack(anchor='w')
            self.target = tk.Text(right, height=4, wrap='word')
            self.target.pack(fill='x')
            actions = ttk.Frame(right)
            actions.pack(fill='x', pady=6)
            ttk.Button(actions, text='Save edit', command=self.save_edit).pack(side='left')
            ttk.Button(actions, text='Export CSV…', command=self.export).pack(side='left', padx=5)
            ttk.Button(actions, text='Import translated CSV…', command=self.import_translations).pack(side='left')
            ttk.Button(actions, text='Install in game', command=self.install_in_game).pack(side='left', padx=5)
            translation = ttk.Frame(right)
            translation.pack(fill='x', pady=5)
            self.provider_label = ttk.Label(translation, text=DEEPSEEK_LABEL)
            self.provider_label.pack(side='left')
            ttk.Checkbutton(translation, text='Include review candidates', variable=self.include_review).pack(side='left', padx=7)
            self.translate_button = ttk.Button(translation, text='Translate with DeepSeek', command=self.translate)
            self.translate_button.pack(side='left')
            ttk.Button(translation, text='Cancel job', command=self.stop.set).pack(side='right')
            ttk.Label(right, text='DeepSeek V4.1 Flash uses your saved API key. Extracted files stay in this project.').pack(anchor='w')
            ttk.Label(self, textvariable=self.status, padding=10, wraplength=1320).pack(fill='x')
            self.refresh()
            self.after(120, self.poll)

        def filter_debounce(self):
            if self.filter_job:
                self.after_cancel(self.filter_job)
            self.filter_job = self.after(200, self.render)

        def browse_game(self):
            if self.busy: return
            path = filedialog.askdirectory(initialdir=self.game.get())
            if path:
                self.game.set(path)
                self.refresh()

        def refresh(self):
            if self.busy: return
            try:
                self.mods = {m['id']: m for m in discover(Path(self.game.get()))}
                self.mod_tree.delete(*self.mod_tree.get_children())
                for m in self.mods.values():
                    self.mod_tree.insert('', 'end', iid=m['id'], text=m['name'], values=(m['origin'],))
                self.status.set(f'{len(self.mods)} mods found. Select a mod to load its project or extract Chinese text.')
            except Exception as exc: messagebox.showerror('Mod discovery failed', str(exc))

        def add_mod(self):
            if self.busy: return
            path = filedialog.askdirectory()
            if not path: return
            import hashlib
            ident = Path(path).name + '-' + hashlib.sha256(path.encode()).hexdigest()[:8]
            if ident not in self.mods:
                self.mods[ident] = {'id': ident, 'name': Path(path).name, 'path': path, 'origin': 'Custom'}
                self.mod_tree.insert('', 'end', iid=ident, text=Path(path).name, values=('Custom',))
            self.mod_tree.selection_set(ident)

        def select_mod(self, _=None):
            if self.busy: return
            selection = self.mod_tree.selection()
            if not selection: return
            self.current = selection[0]
            self.folder = APP / 'projects' / self.current
            path = self.folder / 'project.json'
            try:
                self.project = read_json(path) if path.exists() else None
                self.render()
                self.status.set(self.summary() if self.project else 'Press Extract Chinese text to scan ' + self.mods[self.current]['name'])
            except Exception as exc: messagebox.showerror('Project load failed', str(exc))

        def summary(self):
            p = self.project
            return f'{p["mod"]["name"]}: {len(p["units"]):,} unique strings. Categories: {p["coverage"]["categories"]}. Coverage: {p["coverage"]["counts"]}.'

        def render(self):
            self.filter_job = None
            self.table.delete(*self.table.get_children())
            if not self.project: return
            term = self.search.get().casefold()
            category = {'Player text': 'player_text', 'Review candidates': 'review', 'Technical': 'technical'}.get(self.category.get())
            self.unit_map = {u['id']: u for u in self.project['units']}
            for u in self.project['units']:
                if category and category != u['category']: continue
                if self.category.get() == 'Untranslated' and u['translation']: continue
                if term and term not in (u['source'] + u['translation'] + json.dumps(u['occurrences'], ensure_ascii=False)).casefold(): continue
                self.table.insert('', 'end', iid=u['id'], values=(u['category'], u['source'].replace('\n', ' ↵ ')[:180], u['translation'].replace('\n', ' ↵ ')[:180]))

        def select_unit(self, _=None):
            selection = self.table.selection()
            if not selection: return
            u = self.unit_map[selection[0]]
            self.source.configure(state='normal')
            self.source.delete('1.0', 'end')
            self.source.insert('1.0', u['source'] + '\n\n' + '\n'.join(o['file'] + '  ' + o['location'] for o in u['occurrences'][:30]))
            self.source.configure(state='disabled')
            self.target.delete('1.0', 'end')
            self.target.insert('1.0', u['translation'])

        def save_edit(self):
            if self.busy: return
            selection = self.table.selection()
            if not selection: return
            u = self.unit_map[selection[0]]
            value = self.target.get('1.0', 'end-1c')
            error = validate_translation(u['source'], value)
            if error:
                messagebox.showerror('Translation needs correction', error)
                return
            u['translation'], u['status'] = value, 'edited' if value else 'untranslated'
            save_project(self.project, self.folder)
            self.table.set(u['id'], 'translation', value.replace('\n', ' ↵ ')[:180])
            self.status.set('Translation saved. CSV, JSON and dictionary exports updated.')

        def start(self, work):
            if self.busy: return
            self.busy = True
            self.stop.clear()
            self.mod_tree.state(['disabled'])
            self.extract_button.state(['disabled'])
            self.translate_button.state(['disabled'])
            self.status.set('Working…')
            def worker():
                try: self.queue.put(('done', work()))
                except Exception as exc: self.queue.put(('error', str(exc)))
            threading.Thread(target=worker, daemon=True).start()

        def progress(self, text): self.queue.put(('progress', text))

        def poll(self):
            latest = None
            while True:
                try: event, payload = self.queue.get_nowait()
                except queue.Empty: break
                if event == 'progress':
                    latest = payload
                    continue
                latest = None
                self.busy = False
                self.mod_tree.state(['!disabled'])
                self.extract_button.state(['!disabled'])
                self.translate_button.state(['!disabled'])
                if event == 'error':
                    self.status.set(payload)
                    messagebox.showerror('Job stopped', payload)
                else:
                    self.project = read_json(self.folder / 'project.json')
                    self.render()
                    self.status.set(self.summary() + (' ' + str(payload) if payload else ''))
                if self.current:
                    self.mod_tree.selection_set(self.current)
            if latest: self.status.set(latest)
            self.after(120, self.poll)

        def extract_selected(self):
            if self.busy or not self.current: return
            mod, folder = self.mods[self.current], self.folder
            self.start(lambda: (extract(mod, folder, self.progress, self.stop.is_set), None)[1])

        def translate(self):
            if self.busy or not self.project: return
            from translation import translate
            project, folder, review = self.project, self.folder, self.include_review.get()
            self.start(lambda: translate(project, folder, progress=self.progress, stop=self.stop.is_set, include_review=review))

        def export(self):
            if self.busy or not self.project: return
            path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile=self.current + '-strings.csv')
            if path:
                export_csv(self.project, path)
                self.status.set('Exported ' + path)

        def install_in_game(self):
            if self.busy or not self.project: return
            from installer import install
            try:
                result = install(self.project, Path(self.game.get()))
                self.status.set(f'Installed {result["count"]:,} saved translations. Restart the game to use them.')
            except Exception as exc:
                messagebox.showerror('Installation failed', str(exc))

        def import_translations(self):
            if self.busy or not self.project: return
            path = filedialog.askopenfilename(filetypes=[('CSV translation file', '*.csv')])
            if not path: return
            try:
                count = import_csv(self.project, path)
                save_project(self.project, self.folder)
                self.render()
                self.status.set(f'Imported {count:,} rows.')
            except Exception as exc: messagebox.showerror('CSV import failed', str(exc))

        def open_folder(self):
            if self.folder and self.folder.exists():
                if os.name == 'nt': os.startfile(self.folder)
                else: subprocess.Popen(['xdg-open', str(self.folder)])

        def coverage(self):
            if not self.project: return
            window = tk.Toplevel(self)
            window.title('Extraction coverage — ' + self.project['mod']['name'])
            text = tk.Text(window, width=120, height=38, wrap='word')
            text.pack(fill='both', expand=True)
            coverage = self.project['coverage']
            exceptional = [f for f in coverage['files'] if f['status'] in ('partial', 'unreadable') or f.get('runtime_review')]
            text.insert('1.0', json.dumps({**coverage, 'files': exceptional}, ensure_ascii=False, indent=2))
            text.configure(state='disabled')

        def close(self):
            if self.busy:
                self.stop.set()
                self.status.set('Cancelling. Close again when the current job has stopped and saved its progress.')
                return
            self.destroy()

    App().mainloop()


def main():
    parser = argparse.ArgumentParser(description='Extract Chinese text from Tale of Immortal mods')
    parser.add_argument('--advanced', action='store_true', help='Open the detailed translation editor')
    parser.add_argument('--game', type=Path, default=GAME)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('list')
    scan = sub.add_parser('extract')
    scan.add_argument('mod', help='Mod ID, folder/DLL path, or all')
    scan.add_argument('--output', type=Path, default=APP / 'projects')
    trans = sub.add_parser('translate')
    trans.add_argument('project', type=Path)
    trans.add_argument('--target', default='en')
    trans.add_argument('--glossary', type=Path)
    trans.add_argument('--include-review', action='store_true')
    imp = sub.add_parser('import-csv')
    imp.add_argument('project', type=Path)
    imp.add_argument('csv', type=Path)
    inst = sub.add_parser('install', help='Install a saved project into the game')
    inst.add_argument('project', type=Path)
    remove = sub.add_parser('uninstall', help='Remove one mod’s installed translations')
    remove.add_argument('mod')
    sub.add_parser('installed', help='List installed translations')
    args = parser.parse_args()
    if args.command is None:
        if args.advanced:
            gui()
        else:
            from desktop import App
            App().mainloop()
        return
    if args.command in ('install', 'uninstall', 'installed'):
        from installer import install, uninstall, installation_status
        if args.command == 'install':
            folder = args.project if args.project.is_dir() else args.project.parent
            result = install(read_json(folder / 'project.json'), args.game)
        elif args.command == 'uninstall':
            result = uninstall(args.mod, args.game)
        else:
            result = installation_status(args.game)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command in ('translate', 'import-csv'):
        folder = args.project if args.project.is_dir() else args.project.parent
        project = read_json(folder / 'project.json')
        if args.command == 'translate':
            from translation import translate
            result = translate(project, folder, target=args.target, progress=print,
                               glossary=args.glossary, include_review=args.include_review)
        else:
            result = import_csv(project, args.csv)
            save_project(project, folder)
        print(json.dumps(result))
        return
    mods = discover(args.game)
    if args.command == 'list':
        print(json.dumps(mods, ensure_ascii=False, indent=2))
        return
    selected = mods if args.mod == 'all' else [m for m in mods if m['id'] == args.mod]
    if not selected and Path(args.mod).exists():
        path = Path(args.mod).resolve()
        import hashlib
        selected = [{'id': path.stem + '-' + hashlib.sha256(str(path).encode()).hexdigest()[:8], 'name': path.stem, 'path': str(path), 'origin': 'Custom'}]
    if not selected:
        parser.error('No matching mod ID or folder')
    atomic_json(args.output / 'inventory.json', mods)
    for mod in selected:
        p = extract(mod, args.output / mod['id'], print)
        print(json.dumps({'mod': mod['id'], 'strings': len(p['units']), 'coverage': p['coverage']['counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
