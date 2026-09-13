"""Simple select-mod / translate / result desktop window."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from app_config import APP_DIR, installed_game, CONCURRENCY_CHOICES, translation_concurrency, save_preferences
from extractor import APP, atomic_json, discover
from mod_workflow import run_job

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Guigu Mod Translator')
        self.geometry('800x700')
        self.minsize(650, 650)
        self.configure(bg='#f5f6fa')
        self.game = installed_game()
        self.mods = {}
        self.busy = False
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.folder = None
        self.search = tk.StringVar()
        self.concurrency = tk.IntVar(value=translation_concurrency())
        self.status = tk.StringVar(value='Finding your mods…')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#f5f6fa')
        style.configure('TLabel', background='#f5f6fa', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 24, 'bold'), foreground='#17213c')
        style.configure('Sub.TLabel', foreground='#667086')
        style.configure('Action.TButton', font=('Segoe UI', 12, 'bold'), padding=(20, 14),
                        foreground='white', background='#385ee8', borderwidth=0)
        style.map('Action.TButton', background=[('disabled', '#bcc6e8'), ('active', '#2446c2')])
        style.configure('Treeview', font=('Segoe UI', 11), rowheight=37, borderwidth=0)
        menu = tk.Menu(self)
        options = tk.Menu(menu, tearoff=False)
        options.add_command(label='Choose game folder…', command=self.choose_game)
        options.add_command(label='Refresh mods', command=self.refresh)
        options.add_separator()
        options.add_command(label='Translation editor…', command=self.editor)
        options.add_command(label='Open saved translations', command=self.open_folder)
        options.add_command(label='Install saved translations', command=self.install_saved)
        options.add_command(label='Remove selected mod’s translations', command=self.remove_installed)
        menu.add_cascade(label='Options', menu=options)
        self.configure(menu=menu)
        body = ttk.Frame(self, padding=(30, 25))
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Translate your mods', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Choose a mod. Translate and install it for your next game launch.', style='Sub.TLabel').pack(anchor='w', pady=(6, 20))
        ttk.Label(body, text='Search mods', style='Sub.TLabel').pack(anchor='w')
        ttk.Entry(body, textvariable=self.search, font=('Segoe UI', 11)).pack(fill='x', pady=(5, 12))
        self.search.trace_add('write', lambda *_: self.render())
        list_frame = ttk.Frame(body)
        list_frame.pack(fill='both', expand=True)
        self.list = ttk.Treeview(list_frame, show='tree', selectmode='browse', height=7)
        self.list.column('#0', width=650)
        scroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        self.list.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.list.bind('<<TreeviewSelect>>', self.selected)
        self.choose = ttk.Button(body, text='Choose game folder…', command=self.choose_game)
        speed = ttk.Frame(body)
        speed.pack(fill='x', pady=(12, 0))
        ttk.Label(speed, text='Parallel requests').pack(side='left')
        self.parallel = ttk.Combobox(speed, textvariable=self.concurrency, values=CONCURRENCY_CHOICES, state='readonly', width=6)
        self.parallel.pack(side='left', padx=10)
        self.parallel.bind('<<ComboboxSelected>>', self.change_concurrency)
        self.action = ttk.Button(body, text='Translate and install', style='Action.TButton', command=self.translate)
        self.action.pack(fill='x', pady=(20, 12))
        self.action.state(['disabled'])
        self.bar = ttk.Progressbar(body, mode='indeterminate')
        ttk.Label(body, textvariable=self.status, wraplength=720).pack(anchor='w', pady=(5, 8))
        self.result_button = ttk.Button(body, text='Open translations', command=self.open_folder)
        ttk.Label(body, text='Installs in-game text translations. Restart the game after changes.', style='Sub.TLabel').pack(anchor='w', pady=(6, 0))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.after(10, self.refresh)

    def refresh(self):
        if self.busy:
            return
        if not self.game:
            self.status.set('Choose your Tale of Immortal game folder to get started.')
            self.choose.pack(before=self.action, fill='x', pady=10)
            return
        self.status.set('Finding your mods…')
        self.busy = True
        self.action.state(['disabled'])
        def scan():
            try:
                self.events.put(('mods', discover(self.game)))
            except Exception:
                self.events.put(('error', 'Could not read your mods. Choose the game folder from Options.'))
        threading.Thread(target=scan, daemon=True).start()

    def choose_game(self):
        if self.busy:
            return
        path = filedialog.askdirectory(title='Select the folder containing guigubahuang.exe')
        if not path:
            return
        if not (Path(path) / 'guigubahuang.exe').is_file():
            messagebox.showerror('Game not found', 'Choose the Tale of Immortal folder containing guigubahuang.exe.')
            return
        self.game = Path(path)
        save_preferences(game=str(self.game))
        self.choose.pack_forget()
        self.refresh()

    def render(self):
        selected = self.list.selection()
        self.list.delete(*self.list.get_children())
        term = self.search.get().casefold()
        for ident, mod in self.mods.items():
            if term in (mod['name'] + ' ' + ident).casefold():
                self.list.insert('', 'end', iid=ident, text=mod['name'])
        if selected and self.list.exists(selected[0]):
            self.list.selection_set(selected[0])
        self.selected()

    def selected(self, _=None):
        if self.busy:
            return
        selection = self.list.selection()
        self.action.state(['!disabled'] if selection else ['disabled'])
        if selection:
            self.folder = APP / 'projects' / selection[0]
            self.status.set('Ready to translate ' + self.mods[selection[0]]['name'])

    def translate(self):
        if self.busy:
            self.stop.set()
            self.action.state(['disabled'])
            self.status.set('Stopping new requests. Finishing requests already sent and saving progress…')
            return
        selection = self.list.selection()
        if not selection:
            return
        mod = self.mods[selection[0]]
        self.folder = APP / 'projects' / mod['id']
        self.busy = True
        concurrency = self.concurrency.get()
        self.parallel.configure(state='disabled')
        self.stop.clear()
        self.action.configure(text='Cancel')
        self.result_button.pack_forget()
        self.bar.pack(before=self.action, fill='x', pady=(10, 0))
        self.bar.start(14)
        def job():
            try:
                result = run_job(mod, self.folder, lambda message: self.events.put(('progress', message)), self.stop.is_set, game=self.game, concurrency=concurrency)
                self.events.put(('result', result))
            except InterruptedError:
                self.events.put(('error', 'Cancelled. Previously saved translations are kept.'))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def finish(self):
        self.busy = False
        self.parallel.configure(state='readonly')
        self.bar.stop()
        self.bar.pack_forget()
        self.action.configure(text='Translate and install')
        self.action.state(['!disabled'] if self.list.selection() else ['disabled'])

    def change_concurrency(self, _=None):
        try:
            save_preferences(concurrency=self.concurrency.get())
        except OSError as exc:
            self.status.set('Could not save parallel request setting: ' + str(exc))

    def poll(self):
        latest = None
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                latest = value
                continue
            latest = None
            if kind == 'mods':
                self.busy = False
                self.mods = {m['id']: m for m in value}
                self.render()
                self.status.set('Click a mod to get started.' if value else 'No downloaded mods found. Subscribe to a mod in Steam Workshop, then refresh.')
            else:
                self.finish()
                if kind == 'error':
                    self.status.set(value)
                else:
                    state = value['state']
                    if state == 'success':
                        installed = value.get('installation')
                        if installed:
                            self.status.set(f'Installed {installed["count"]:,} translations. Restart the game to use them.')
                        else:
                            self.status.set('Translations saved, but installation did not complete. Use Options → Install saved translations.')
                    elif state == 'empty':
                        self.status.set('No readable Chinese text was found. You can check the coverage report in the saved files.')
                    elif state == 'cancelled':
                        self.status.set('Cancelled. Saved progress will be reused next time.')
                    else:
                        installed = value.get('installation')
                        if installed:
                            self.status.set(f'Installed {installed["count"]:,} translations. Some text still needs review. Restart the game to use the installed text.')
                        else:
                            self.status.set(f'{value["count"]:,} translations saved. Some text still needs review; see the saved files.')
                    self.result_button.pack(before=self.action, pady=(10, 0))
        if latest:
            self.status.set(latest)
        self.after(100, self.poll)

    def open_folder(self):
        folder = self.folder if self.folder and self.folder.exists() else APP / 'projects'
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)
        else:
            subprocess.Popen(['xdg-open', str(folder)])

    def editor(self):
        if self.busy:
            return
        args = [sys.executable, '--advanced'] if getattr(sys, 'frozen', False) else [sys.executable, str(APP_DIR / 'entry.py'), '--advanced']
        subprocess.Popen(args)

    def install_saved(self):
        if self.busy or not self.list.selection():
            return
        from extractor import read_json
        from installer import install
        selection = self.list.selection()[0]
        folder = APP / 'projects' / selection
        try:
            project = read_json(folder / 'project.json')
            # Discovery is authoritative if the game or Workshop library moved.
            project['mod'] = self.mods[selection]
            result = install(project, self.game)
            self.status.set(f'Installed {result["count"]:,} translations. Restart the game to use them.')
        except FileNotFoundError:
            self.status.set('No saved translation project yet. Click Translate and install first.')
        except Exception as exc:
            self.status.set('Installation failed: ' + str(exc))

    def remove_installed(self):
        if self.busy or not self.list.selection():
            return
        from installer import uninstall
        try:
            result = uninstall(self.list.selection()[0], self.game)
            self.status.set('Translations removed. Restart the game. Saved translations are kept.'
                            if result['state'] == 'removed' else 'This mod has no installed translations.')
        except Exception as exc:
            self.status.set('Could not remove translations: ' + str(exc))

    def close(self):
        if self.busy:
            self.stop.set()
            self.status.set('Waiting for requests already sent to finish and save. Close again when stopped.')
            return
        self.destroy()
