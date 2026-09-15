"""Simple select-mod / translate / result desktop window."""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from app_config import APP_DIR, APP_VERSION, installed_game, CONCURRENCY_CHOICES, translation_concurrency, save_preferences
from app_config import BATCH_SIZE_CHOICES, translation_batch_size, is_friends_build
from extractor import APP, atomic_json, discover
from mod_workflow import run_job
from installer import installation_message
from translation_cost import estimate_mod, format_pence, full_translation_allowed, PRICING_NOTE
from app_config import bulk_price_pence
from bulk_translation import plan_bulk, money, run_bulk, bulk_summary

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Guigu Mod Translator ' + APP_VERSION)
        self.geometry('800x800')
        self.minsize(650, 770)
        self.configure(bg='#f5f6fa')
        self.game = installed_game()
        self.mods = {}
        self.estimates = {}
        self.estimate_stop = threading.Event()
        self.friends = is_friends_build()
        self.title('Guigu Mod Translator ' + APP_VERSION + ' — ' + ('Friends' if self.friends else 'Personal'))
        self.busy = False
        self.bulk_running = False
        self.bulk_price = tk.IntVar(value=bulk_price_pence())
        self.bulk_price_label = tk.StringVar()
        self.bulk_note = tk.StringVar()
        self.price_save_timer = None
        self.setting_up = False
        self.setup_ready = False
        self.collecting_logs = False
        self.log_status = tk.StringVar()
        self.access_note = tk.StringVar()
        self.balance_label = tk.StringVar(value='Balance: checking…')
        self.balance_detail = tk.StringVar()
        self.balance_profile = {}
        self.balance_refreshing = False
        self.next_balance_refresh = 0
        self.personal_key = False
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
        options.add_command(label='Check game setup', command=self.start_setup)
        options.add_command(label='Collect logs', command=self.collect_logs)
        options.add_command(label='API key…', command=self.api_key_settings)
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
        balance_header = ttk.Frame(body)
        balance_header.pack(fill='x', pady=(0, 8))
        balance_left = ttk.Frame(balance_header)
        balance_left.pack(side='left', fill='x', expand=True)
        ttk.Label(balance_left, textvariable=self.balance_label, font=('Segoe UI', 13, 'bold'), foreground='#17213c').pack(anchor='w')
        ttk.Label(balance_left, textvariable=self.balance_detail, style='Sub.TLabel', wraplength=420).pack(anchor='w')
        key_controls = ttk.Frame(balance_header)
        key_controls.pack(side='right', padx=(8, 0))
        self.api_key_button = ttk.Button(key_controls, text='API key…', command=self.api_key_settings)
        self.api_key_button.pack(anchor='e')
        from api_key_dialog import help_link
        self.api_help_button = help_link(key_controls, self)
        self.api_help_button.pack(anchor='e')
        ttk.Label(body, text='Translate your mods', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Choose a mod. Translate and install it for your next game launch.', style='Sub.TLabel').pack(anchor='w', pady=(6, 12))
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
        bulk = ttk.Frame(body)
        bulk.pack(fill='x', pady=(10, 0))
        self.bulk_button = ttk.Button(bulk, text='Translate all', command=self.translate_all)
        self.bulk_button.pack(side='left')
        self.price_slider = tk.Scale(bulk, from_=5, to=200, resolution=5, orient='horizontal',
                                     variable=self.bulk_price, command=self.change_bulk_price,
                                     showvalue=False, highlightthickness=0, bg='#f5f6fa', bd=0)
        self.price_slider.pack(side='left', fill='x', expand=True, padx=10)
        ttk.Label(bulk, textvariable=self.bulk_price_label, width=22).pack(side='right')
        ttk.Label(body, textvariable=self.bulk_note, style='Sub.TLabel', wraplength=580).pack(anchor='w', pady=(3, 0))
        self.action = ttk.Button(body, text='Translate and install', style='Action.TButton', command=self.translate)
        self.action.pack(fill='x', pady=(12, 8))
        self.action.state(['disabled'])
        self.bar = ttk.Progressbar(body, mode='indeterminate')
        self.status_label = ttk.Label(body, textvariable=self.status, wraplength=720)
        self.status_label.pack(anchor='w', pady=(5, 8))
        body.bind('<Configure>', lambda event: self.status_label.configure(wraplength=max(240, event.width - 60)))
        self.result_button = ttk.Button(body, text='Open translations', command=self.open_folder)
        self.setup_retry = ttk.Button(body, text='Retry setup', command=self.start_setup)
        self.steam_install = ttk.Button(body, text='Install game in Steam', command=lambda: os.startfile('steam://install/1468810'))
        footer = ttk.Frame(body)
        footer.pack(fill='x')
        self.logs_button = ttk.Button(footer, text='Collect logs', command=self.collect_logs)
        self.logs_button.pack(side='left')
        ttk.Label(footer, textvariable=self.log_status, style='Sub.TLabel', wraplength=340).pack(side='left', padx=8)
        self.play_button = ttk.Button(footer, text='Launch game', command=self.play)
        self.play_button.pack(side='right')
        ttk.Label(body, text='Installs in-game text translations. Restart the game after changes.', style='Sub.TLabel').pack(anchor='w', pady=(6, 0))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.after(10, self.start_setup)
        self.after(5000, self.check_game_install)
        self.refresh_access()
        self.after(50, self.balance_tick)

    def refresh_access(self):
        from app_config import service_profile
        try:
            self.balance_profile = service_profile()
            self.personal_key = self.balance_profile.get('personal_key', False)
            access_error = False
        except (OSError, ValueError):
            self.personal_key, access_error = False, True
            self.balance_profile = {}
        if access_error:
            note = 'API key needs attention. Open API key to choose translation access.'
        elif self.personal_key:
            note = 'Personal OpenRouter key · uses your credit · no app cost cap.'
        elif self.friends:
            note = ''
        else:
            note = 'DeepSeek V4.1 Flash · estimates in pence (p) · no personal edition limit.'
        self.access_note.set(note)
        self.next_balance_refresh = 0
        self.update_balance_display()
        self.render()

    def update_balance_display(self):
        from translation_balance import tracker, balance_text
        text, detail = balance_text(tracker().snapshot(self.balance_profile))
        self.balance_label.set(text)
        self.balance_detail.set(detail)

    def balance_tick(self):
        self.update_balance_display()
        if not self.balance_refreshing and time.monotonic() >= self.next_balance_refresh:
            profile = dict(self.balance_profile)
            self.balance_refreshing = True
            self.next_balance_refresh = time.monotonic() + 30
            def refresh():
                from translation_balance import tracker
                try:
                    tracker().refresh(profile)
                finally:
                    self.events.put(('balance_refreshed', None))
            threading.Thread(target=refresh, daemon=True).start()
        self.after(500, self.balance_tick)

    def api_key_settings(self):
        if self.busy and not self.setting_up:
            self.status.set('Finish or cancel the current operation before changing API keys.')
            return
        from api_key_dialog import ApiKeyDialog
        def changed(message):
            self.refresh_access()
            self.status.set(message)
        return ApiKeyDialog(self, changed)

    def collect_logs(self):
        # Available during a stuck first launch, a failed setup, or translation.
        # Collection has its own state and never cancels those operations.
        if self.collecting_logs:
            return
        self.collecting_logs = True
        self.logs_button.state(['disabled'])
        self.log_status.set('Collecting…')
        snapshot = {'setup_in_progress': self.setting_up, 'busy': self.busy,
                    'setup_ready': self.setup_ready, 'message': self.status.get()}
        game, handle = self.game, self.winfo_id()
        def job():
            from diagnostics import collect_logs
            try:
                self.events.put(('logs_done', collect_logs(game, snapshot, handle)))
            except Exception as exc:
                self.events.put(('logs_error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def check_game_install(self):
        if not self.game and not self.busy:
            self.game = installed_game()
            if self.game:
                self.choose.pack_forget()
                self.steam_install.pack_forget()
                self.start_setup()
        self.after(5000, self.check_game_install)

    def start_setup(self):
        if self.busy:
            return
        if not self.game:
            self.game = installed_game()
        if not self.game:
            self.refresh()
            return
        self.setting_up = self.busy = True
        self.setup_ready = False
        self.update_bulk_controls()
        self.stop.clear()
        self.estimate_stop.set()
        self.setup_retry.pack_forget()
        self.result_button.pack_forget()
        self.parallel.configure(state='disabled')
        self.batch_choice.configure(state='disabled')
        self.action.configure(text='Cancel setup')
        self.action.state(['!disabled'])
        self.bar.stop()
        self.bar.configure(mode='determinate', maximum=100, value=0)
        self.bar.pack(before=self.action, fill='x', pady=(10, 0))
        def job():
            from game_setup import ensure_setup
            try:
                result = ensure_setup(self.game, lambda percent, message: self.events.put(('setup_progress', (percent, message))), self.stop.is_set)
                self.events.put(('setup_done', result))
            except PermissionError as exc:
                self.events.put(('setup_permission', str(exc)))
            except Exception as exc:
                self.events.put(('setup_error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def play(self):
        if self.busy or not self.game:
            return
        if not self.setup_ready:
            self.start_setup()
            return
        from game_setup import launch_game, game_processes
        try:
            if game_processes(self.game):
                self.status.set('The game is already open. Save and close it before launching to apply new translations.')
            else:
                launch_game(self.game)
                self.status.set('Launching Tale of Immortal…')
        except Exception as exc:
            self.status.set(str(exc))

    def refresh(self):
        if self.busy:
            return
        if not self.game:
            self.status.set('Install Tale of Immortal in Steam, then click Retry setup. If it is already installed, choose its folder.')
            self.choose.pack(before=self.action, fill='x', pady=10)
            self.setup_retry.pack(before=self.action, fill='x', pady=5)
            self.steam_install.pack(before=self.action, fill='x', pady=5)
            return
        if not self.setup_ready:
            self.start_setup()
            return
        self.status.set('Finding your mods…')
        self.busy = True
        self.update_bulk_controls()
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
        self.steam_install.pack_forget()
        self.setup_ready = False
        self.start_setup()

    def find_destinies(self):
        if self.busy or not self.game:
            return
        if not self.setup_ready:
            self.start_setup()
            return
        from destinies import PROJECT_ID, scan_destinies, destiny_report
        from installer import install_detector
        self.busy = True
        self.update_bulk_controls()
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
        if not self.setup_ready:
            self.start_setup()
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
        elif not self.friends or self.personal_key:
            access = 'Available'
        elif estimate is None:
            access = 'Checking cost…'
        elif estimate.get('error') or not estimate.get('complete'):
            access = 'Estimate unavailable'
        else:
            access = 'Available' if full_translation_allowed(estimate) else 'Over 5p limit'
        return text, access

    def can_translate(self, ident):
        from destinies import PROJECT_ID
        return ident == PROJECT_ID or not self.friends or self.personal_key or full_translation_allowed(self.estimates.get(ident))

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
        self.update_bulk_controls()
        if self.busy:
            return
        selection = self.list.selection()
        self.action.state(['!disabled'] if self.setup_ready and selection and self.can_translate(selection[0]) else ['disabled'])
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
            self.update_bulk_controls()
            self.action.state(['disabled'])
            self.status.set('Stopping setup safely…' if self.setting_up else 'Stopping new requests. Finishing requests already sent and saving progress…')
            return
        if not self.setup_ready:
            self.start_setup()
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
        self.update_bulk_controls()
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
        self.bulk_running = False
        self.next_balance_refresh = 0
        self.parallel.configure(state='readonly')
        self.batch_choice.configure(state='readonly')
        self.bar.stop()
        self.bar.configure(mode='indeterminate', value=0)
        self.bar.pack_forget()
        self.action.configure(text='Translate and install')
        self.selected()

    def update_bulk_controls(self):
        self.bulk_price_label.set('Up to ' + money(self.bulk_price.get()) + ' per mod')
        if self.bulk_running:
            self.bulk_button.configure(text='Cancel all')
            self.bulk_button.state(['disabled'] if self.stop.is_set() else ['!disabled'])
            self.price_slider.configure(state='disabled')
            return
        self.bulk_button.configure(text='Translate all')
        self.price_slider.configure(state='disabled' if self.busy else 'normal')
        plan = plan_bulk(list(self.mods.values()), self.estimates, self.bulk_price.get(),
                         limited=self.friends and not self.personal_key)
        if plan['pending']:
            note = f'Calculating prices for {plan["pending"]} mods…'
        else:
            note = f'{len(plan["mods"])} matching mods · ~{money(plan["total_pence"])} combined estimate'
            if plan['excluded']:
                note += f' · {plan["excluded"]} excluded'
        self.bulk_note.set(note + '. Price is per mod.')
        ready = self.setup_ready and not self.busy and not plan['pending'] and bool(plan['mods'])
        self.bulk_button.state(['!disabled'] if ready else ['disabled'])

    def change_bulk_price(self, _=None):
        self.update_bulk_controls()
        if self.price_save_timer is not None:
            self.after_cancel(self.price_save_timer)
        self.price_save_timer = self.after(350, self.save_bulk_price)

    def save_bulk_price(self):
        self.price_save_timer = None
        try:
            save_preferences(bulk_price_pence=self.bulk_price.get())
        except OSError as exc:
            self.status.set('Could not save the price filter: ' + str(exc))

    def translate_all(self):
        if self.bulk_running:
            self.stop.set()
            self.action.state(['disabled'])
            self.update_bulk_controls()
            self.status.set('Stopping the queue. Finishing requests already sent and saving progress…')
            return
        if self.busy or not self.setup_ready:
            return
        limit = self.bulk_price.get()
        plan = plan_bulk(list(self.mods.values()), self.estimates, limit,
                         limited=self.friends and not self.personal_key)
        if plan['pending'] or not plan['mods']:
            self.update_bulk_controls()
            return
        self.busy = self.bulk_running = True
        self.stop.clear()
        self.parallel.configure(state='disabled')
        self.batch_choice.configure(state='disabled')
        self.action.configure(text='Cancel all')
        self.action.state(['!disabled'])
        self.result_button.pack_forget()
        self.bar.stop()
        self.bar.configure(mode='determinate', maximum=100, value=0)
        self.bar.pack(before=self.action, fill='x', pady=(10, 0))
        self.update_bulk_controls()
        concurrency, batch_size, game = self.concurrency.get(), self.batch_size.get(), self.game
        self.folder = APP / 'projects'
        self.status.set(f'Starting {len(plan["mods"])} mods, cheapest first. Saved translations will be reused.')
        def job():
            try:
                result = run_bulk(plan['mods'], APP / 'projects', limit,
                                  lambda p, m: self.events.put(('bulk_progress', (p, m))),
                                  self.stop.is_set, game=game, concurrency=concurrency, batch_size=batch_size)
                self.events.put(('bulk_result', result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

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
            if kind == 'balance_refreshed':
                self.balance_refreshing = False
                self.update_balance_display()
                continue
            if kind in ('logs_done', 'logs_error'):
                self.collecting_logs = False
                self.logs_button.state(['!disabled'])
                if kind == 'logs_error':
                    self.log_status.set('Could not collect logs. Click to retry.')
                elif value['copied'] and value['path']:
                    self.log_status.set('Copied · Guigu-Logs.txt saved beside EXE')
                elif value['copied']:
                    self.log_status.set('Logs copied — paste to send them')
                elif value['path']:
                    self.log_status.set('Saved Guigu-Logs.txt beside EXE')
                else:
                    path = filedialog.asksaveasfilename(title='Save collected logs', initialfile='Guigu-Logs.txt',
                                                       defaultextension='.txt', filetypes=[('Text report', '*.txt')])
                    try:
                        if path:
                            Path(path).write_text(value['text'], encoding='utf-8-sig')
                        self.log_status.set('Logs saved.' if path else 'Logs not saved. Click to retry.')
                    except OSError:
                        self.log_status.set('Could not save logs. Click to retry.')
                continue
            if kind == 'progress':
                latest = value
                continue
            if kind in ('setup_progress', 'bulk_progress'):
                percent, message = value
                self.bar.configure(value=percent)
                latest = f'{percent:.0f}% · {message}'
                continue
            if kind.startswith('setup_'):
                latest = None
                self.setting_up = False
                self.finish()
                if kind == 'setup_done':
                    if value.get('game'):
                        self.game = Path(value['game'])
                    self.setup_ready = True
                    self.refresh()
                else:
                    self.status.set(value)
                    self.setup_retry.pack(before=self.action, fill='x', pady=5)
                    if kind == 'setup_permission':
                        from game_setup import restart_elevated
                        self.status.set('Windows needs permission to set up this game. Requesting access…')
                        self.update_idletasks()
                        try:
                            restart_elevated(self.game)
                            self.destroy()
                            return
                        except Exception as exc:
                            self.status.set(str(exc))
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
            if kind == 'bulk_result':
                self.finish()
                self.folder = APP / 'projects'
                self.status.set(bulk_summary(value))
                self.result_button.pack(before=self.action, pady=(10, 0))
                continue
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
        if not self.setup_ready:
            self.start_setup()
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
        if self.collecting_logs:
            self.log_status.set('Finishing log collection. Close again when done.')
            return
        if self.busy:
            self.stop.set()
            self.status.set('Stopping setup safely. Close again when stopped.' if self.setting_up else 'Waiting for requests already sent to finish and save. Close again when stopped.')
            return
        self.estimate_stop.set()
        self.destroy()
