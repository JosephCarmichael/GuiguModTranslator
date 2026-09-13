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
from app_config import BATCH_SIZE_CHOICES, translation_batch_size, is_friends_build
from extractor import APP, atomic_json, discover
from mod_workflow import run_job
from installer import installation_message
from translation_cost import estimate_mod, format_pence, full_translation_allowed, PRICING_NOTE

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Guigu Mod Translator')
        self.geometry('800x700')
        self.minsize(650, 650)
        self.configure(bg='#f5f6fa')
        self.game = installed_game()
        self.mods = {}
        self.estimates = {}
        self.estimate_stop = threading.Event()
        self.friends = is_friends_build()
        self.title('Guigu Mod Translator — ' + ('Friends' if self.friends else 'Personal'))
        self.busy = False
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.folder = None
        self.current_selection = None
        self.search = tk.StringVar()
        self.concurrency = tk.IntVar(value=translation_concurrency())
        self.batch_size = tk.IntVar(value=translation_batch_size())
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
        options.add_command(label='Find untranslated destinies', command=self.find_destinies)
        options.add_command(label='About cost estimates…', command=lambda: messagebox.showinfo('Cost estimates', PRICING_NOTE))
        options.add_separator()
        options.add_command(label='Translation editor…', command=self.editor)
        options.add_command(label='Open saved translations', command=self.open_folder)
        options.add_command(label='Install saved translations', command=self.install_saved)
        options.add_command(label='Remove selected mod’s translations', command=self.remove_installed)
        menu.add_cascade(label='Options', menu=options)
        self.configure(menu=menu)
        body = ttk.Frame(self, padding=(24, 16))
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Translate your mods', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Choose a mod. Translate and install it for your next game launch.', style='Sub.TLabel').pack(anchor='w', pady=(6, 20))
        ttk.Label(body, text='Search mods', style='Sub.TLabel').pack(anchor='w')
        ttk.Entry(body, textvariable=self.search, font=('Segoe UI', 11)).pack(fill='x', pady=(5, 12))
        self.search.trace_add('write', lambda *_: self.render())
        list_frame = ttk.Frame(body)
        list_frame.pack(fill='both', expand=True)
        self.list = ttk.Treeview(list_frame, columns=('cost', 'access'), show='tree headings', selectmode='browse', height=4)
        self.list.heading('#0', text='Mod')
        self.list.heading('cost', text='Full-mod estimate')
        self.list.heading('access', text='Translation')
        self.list.column('#0', width=380, minwidth=180)
        self.list.column('cost', width=125, minwidth=110, stretch=False, anchor='e')
        self.list.column('access', width=155, minwidth=140, stretch=False)
        scroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        self.list.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.list.bind('<<TreeviewSelect>>', self.selected)
        ttk.Label(body, text=('Friends: full mods up to 0.5p (£0.005). Destiny menu always available.' if self.friends else
                             'DeepSeek V4.1 Flash · estimates in pence (p) · no personal edition limit.'),
                  style='Sub.TLabel', wraplength=580).pack(anchor='w', pady=(5, 0))
        self.choose = ttk.Button(body, text='Choose game folder…', command=self.choose_game)
        speed = ttk.Frame(body)
        speed.pack(fill='x', pady=(12, 0))
        ttk.Label(speed, text='Max parallel requests').pack(side='left')
        self.parallel = ttk.Combobox(speed, textvariable=self.concurrency, values=CONCURRENCY_CHOICES, state='readonly', width=6)
        self.parallel.pack(side='left', padx=10)
        self.parallel.bind('<<ComboboxSelected>>', self.change_concurrency)
        ttk.Label(speed, text='Entries per request').pack(side='left', padx=(15, 0))
        self.batch_choice = ttk.Combobox(speed, textvariable=self.batch_size, values=BATCH_SIZE_CHOICES, state='readonly', width=6)
        self.batch_choice.pack(side='left', padx=10)
        self.batch_choice.bind('<<ComboboxSelected>>', self.change_batch_size)
        destiny_actions = ttk.Frame(body)
        destiny_actions.pack(fill='x', pady=(10, 0))
        self.destiny_button = ttk.Button(destiny_actions, text='Find untranslated destinies', command=self.find_destinies)
        self.destiny_button.pack(side='left')
        self.translate_destiny_button = ttk.Button(destiny_actions, text='Translate destiny menu', command=self.translate_destinies)
        self.translate_destiny_button.pack(side='left', padx=(10, 0))
        self.action = ttk.Button(body, text='Translate and install', style='Action.TButton', command=self.translate)
        self.action.pack(fill='x', pady=(20, 12))
        self.action.state(['disabled'])
        self.bar = ttk.Progressbar(body, mode='indeterminate')
        self.status_label = ttk.Label(body, textvariable=self.status, wraplength=720)
        self.status_label.pack(anchor='w', pady=(5, 8))
        body.bind('<Configure>', lambda event: self.status_label.configure(wraplength=max(240, event.width - 60)))
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

    def find_destinies(self):
        if self.busy or not self.game:
            return
        from destinies import PROJECT_ID, scan_destinies, destiny_report
        from installer import install_detector
        self.busy = True
        self.stop.clear()
        self.action.state(['disabled'])
        self.folder = APP / 'projects' / PROJECT_ID
        self.status.set('Looking for untranslated destiny names and hover descriptions…')
        self.bar.pack(before=self.action, fill='x', pady=(10, 0))
        self.bar.start(14)
        def job():
            try:
                changed = install_detector(self.game)
                project = scan_destinies(self.game, self.folder,
                    lambda message: self.events.put(('progress', message)), self.stop.is_set)
                self.events.put(('destinies', (project['mod'], destiny_report(project), changed)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def translate_destinies(self):
        if self.busy or not self.game:
            return
        from destinies import PROJECT_ID, destiny_mod
        self.mods[PROJECT_ID] = destiny_mod(self.game)
        self.search.set('')
        self.render()
        self.list.selection_set(PROJECT_ID)
        self.selected()
        self.translate()

    def refresh_estimates(self):
        self.estimate_stop.set()
        stop = self.estimate_stop = threading.Event()
        self.estimates = {}
        batch_size, game, mods = self.batch_size.get(), self.game, list(self.mods.values())
        self.render()
        def scan():
            for mod in mods:
                if stop.is_set():
                    return
                try:
                    value = estimate_mod(mod, game, batch_size, stop.is_set)
                except InterruptedError:
                    return
                except Exception:
                    value = {'error': True}
                self.events.put(('estimate', (stop, mod['id'], value)))
        threading.Thread(target=scan, daemon=True).start()

    def cost_columns(self, ident):
        from destinies import PROJECT_ID
        estimate = self.estimates.get(ident)
        text = 'Calculating…' if estimate is None else ('Unavailable' if estimate.get('error') else format_pence(estimate))
        if ident == PROJECT_ID:
            access = 'Always available'
        elif not self.friends:
            access = 'Available'
        elif estimate is None:
            access = 'Checking cost…'
        elif estimate.get('error') or not estimate.get('complete'):
            access = 'Estimate unavailable'
        else:
            access = 'Available' if full_translation_allowed(estimate) else 'Over 0.5p limit'
        return text, access

    def can_translate(self, ident):
        from destinies import PROJECT_ID
        return ident == PROJECT_ID or not self.friends or full_translation_allowed(self.estimates.get(ident))

    def render(self):
        selected = self.list.selection()
        self.list.delete(*self.list.get_children())
        term = self.search.get().casefold()
        for ident, mod in self.mods.items():
            if term in (mod['name'] + ' ' + ident).casefold():
                self.list.insert('', 'end', iid=ident, text=mod['name'], values=self.cost_columns(ident))
        if selected and self.list.exists(selected[0]):
            self.list.selection_set(selected[0])
        self.selected()

    def selected(self, _=None):
        if self.busy:
            return
        selection = self.list.selection()
        self.action.state(['!disabled'] if selection and self.can_translate(selection[0]) else ['disabled'])
        if selection:
            self.folder = APP / 'projects' / selection[0]
            if selection[0] != self.current_selection:
                self.status.set('Ready to translate ' + self.mods[selection[0]]['name'])
            if not self.can_translate(selection[0]):
                self.status.set(self.cost_columns(selection[0])[1] + '. Destiny-menu translation and installing saved translations remain available.')
            self.current_selection = selection[0]
        else:
            self.current_selection = None

    def translate(self):
        if self.busy:
            self.stop.set()
            self.action.state(['disabled'])
            self.status.set('Stopping new requests. Finishing requests already sent and saving progress…')
            return
        selection = self.list.selection()
        if not selection:
            return
        if not self.can_translate(selection[0]):
            self.selected()
            return
        mod = self.mods[selection[0]]
        self.folder = APP / 'projects' / mod['id']
        self.busy = True
        concurrency = self.concurrency.get()
        batch_size = self.batch_size.get()
        self.parallel.configure(state='disabled')
        self.batch_choice.configure(state='disabled')
        self.stop.clear()
        self.action.configure(text='Cancel')
        self.result_button.pack_forget()
        self.bar.pack(before=self.action, fill='x', pady=(10, 0))
        self.bar.start(14)
        def job():
            try:
                result = run_job(mod, self.folder, lambda message: self.events.put(('progress', message)), self.stop.is_set, game=self.game, concurrency=concurrency, batch_size=batch_size)
                self.events.put(('result', result))
            except InterruptedError:
                self.events.put(('error', 'Cancelled. Previously saved translations are kept.'))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def finish(self):
        self.busy = False
        self.parallel.configure(state='readonly')
        self.batch_choice.configure(state='readonly')
        self.bar.stop()
        self.bar.pack_forget()
        self.action.configure(text='Translate and install')
        self.selected()

    def change_concurrency(self, _=None):
        try:
            save_preferences(concurrency=self.concurrency.get())
        except OSError as exc:
            self.status.set('Could not save parallel request setting: ' + str(exc))

    def change_batch_size(self, _=None):
        try:
            save_preferences(batch_size=self.batch_size.get())
            if self.mods:
                self.refresh_estimates()
        except OSError as exc:
            self.status.set('Could not save batch size: ' + str(exc))

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
            if kind == 'estimate':
                generation, ident, estimate = value
                if generation is self.estimate_stop and not generation.is_set():
                    self.estimates[ident] = estimate
                    if self.list.exists(ident):
                        self.list.item(ident, values=self.cost_columns(ident))
                    if not self.busy:
                        self.selected()
                continue
            latest = None
            if kind == 'mods':
                self.busy = False
                from destinies import destiny_mod
                value.append(destiny_mod(self.game))
                self.mods = {m['id']: m for m in value}
                self.refresh_estimates()
                self.status.set('Click a mod to get started.' if value else 'No downloaded mods found. Subscribe to a mod in Steam Workshop, then refresh.')
            else:
                self.finish()
                if kind == 'error':
                    self.status.set(value)
                elif kind == 'destinies':
                    mod, report, changed = value
                    self.mods[mod['id']] = mod
                    self.search.set('')
                    self.render()
                    self.list.selection_set(mod['id'])
                    self.list.see(mod['id'])
                    self.selected()
                    message = f'Found {report["missing_texts"]:,} untranslated destiny texts. Click Translate and install to fill them.'
                    if report['unresolved_fields']:
                        message += f' {len(report["unresolved_fields"]):,} fields still need in-game detection.'
                    if changed or not report['runtime_inventory']:
                        message += ' Restart the game, open character creation, then scan again to include all loaded destinies.'
                    if report.get('runtime_warnings'):
                        message = report['runtime_warnings'][0] + f' Downloaded tables have {report["missing_texts"]:,} missing texts.'
                    self.status.set(message)
                    self.result_button.pack(before=self.action, pady=(10, 0))
                else:
                    state = value['state']
                    if state == 'success':
                        installed = value.get('installation')
                        if installed:
                            self.status.set(installation_message(installed))
                        else:
                            self.status.set('Translations saved, but installation did not complete. Use Options → Install saved translations.')
                    elif state == 'empty':
                        self.status.set('No readable Chinese text was found. You can check the coverage report in the saved files.')
                    elif state == 'cancelled':
                        self.status.set('Cancelled. Saved progress will be reused next time.')
                    else:
                        installed = value.get('installation')
                        if installed:
                            self.status.set(installation_message(installed, partial=True))
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
            self.status.set(installation_message(result))
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
        self.estimate_stop.set()
        self.destroy()
