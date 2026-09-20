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
from app_config import BATCH_SIZE_CHOICES, translation_batch_size, is_friends_build, build_edition
from mod_titles import apply_titles, display_name, load_titles, needs_title, translate_titles
from saved_translations import job_status, scan_statuses, tick
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
        self.scanning_mods = False
        self.titles = load_titles()
        self.saved = {}
        self.title_running = False
        self.title_refresh_pending = False
        self.title_stop = threading.Event()
        self.shared_running = False
        self.update_running = False
        self.update_stop = threading.Event()
        self.available_update = None
        self.prepared_update = None
        self.update_status = tk.StringVar()
        self.thumbnails = {}
        self.detail_photos = {}
        self.estimates = {}
        self.estimate_stop = threading.Event()
        self.friends = is_friends_build()
        self.title('Guigu Mod Translator ' + APP_VERSION + ' — ' + build_edition().title())
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
        self.title_status = tk.StringVar()
        from desktop_view import build_view
        build_view(self)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.after(10, self.start_setup)
        self.after(5000, self.check_game_install)
        self.refresh_access()
        self.after(50, self.balance_tick)
        self.after(1800, self.check_updates)

    def github_settings(self):
        from github_dialog import GitHubDialog
        def changed():
            self.check_updates(manual=True)
            self.refresh_shared()
        return GitHubDialog(self, changed)

    def translation_settings(self):
        if self.busy or self.title_running:
            self.status.set('Wait for translation to finish or cancel it before changing models.')
            return
        from translation_settings import TranslationSettings
        def changed():
            self.refresh_access()
            self.refresh_estimates()
        return TranslationSettings(self, changed)

    def check_updates(self, manual=False):
        if self.update_running or os.environ.get('GUIGU_TRANSLATOR_OFFLINE') == '1':
            return
        self.update_running = True
        if manual:
            self.update_status.set('Checking GitHub for updates…')
        def job():
            from app_updates import check_update
            try:
                self.events.put(('update_checked', (check_update(), manual)))
            except Exception as exc:
                self.events.put(('update_error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def install_update(self):
        if self.update_running or not self.available_update:
            return
        if self.busy or self.title_running:
            self.update_status.set('Update available. Finish or cancel translation before installing it.')
            return
        if not getattr(sys, 'frozen', False):
            self.update_status.set('This is a source checkout. Pull the latest Git commit, or use the portable EXE for automatic updates.')
            return
        if not messagebox.askyesno('Update available',
                f'Install version {self.available_update["version"]}? Your saved translations and settings will be kept.\n\n'
                'The app will restart after the download is verified.', parent=self):
            return
        self.update_running = True
        self.update_stop.clear()
        self.update_button.state(['disabled'])
        def job():
            from app_updates import prepare_update
            try:
                prepared = prepare_update(self.available_update,
                    lambda message: self.events.put(('update_progress', message)), self.update_stop.is_set)
                self.events.put(('update_prepared', prepared))
            except Exception as exc:
                self.events.put(('update_error', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def finish_update(self):
        if not self.prepared_update:
            return
        if self.busy or self.title_running or self.collecting_logs:
            self.update_status.set('Update downloaded. It will install when the current work finishes.')
            self.after(1000, self.finish_update)
            return
        from app_updates import launch_installer
        try:
            launch_installer(self.prepared_update)
        except Exception as exc:
            self.update_status.set('Could not install update: ' + str(exc))
            self.update_running = False
            self.update_button.state(['!disabled'])
            return
        self.estimate_stop.set()
        self.title_stop.set()
        self.destroy()

    def refresh_shared(self):
        if self.shared_running:
            return
        if os.environ.get('GUIGU_TRANSLATOR_OFFLINE') == '1':
            self.start_titles()
            return
        self.shared_running = True
        def job():
            from shared_library import sync_index
            try:
                sync_index()
                self.events.put(('shared_done', ''))
            except Exception as exc:
                self.events.put(('shared_done', str(exc)))
        threading.Thread(target=job, daemon=True).start()

    def prepare_shared_mod(self, mod):
        if os.environ.get('GUIGU_TRANSLATOR_OFFLINE') == '1':
            return
        from shared_library import sync_mod
        try:
            self.events.put(('progress', 'Checking shared translations…'))
            sync_mod(mod)
        except Exception:
            self.events.put(('progress', 'Shared library unavailable. Reusing locally saved text and continuing with your translation settings.'))

    def refresh_thumbnails(self):
        from PIL import ImageTk
        from thumbnails import load_thumbnail
        for ident, mod in self.mods.items():
            image = load_thumbnail(mod)
            self.thumbnails[ident] = ImageTk.PhotoImage(image, master=self) if image else None
            image = load_thumbnail(mod, (206, 104))
            self.detail_photos[ident] = ImageTk.PhotoImage(image, master=self) if image else None

    def update_detail(self):
        selection = self.list.selection()
        enabled = bool(selection) and not self.busy and self.setup_ready
        self.again_button.state(['!disabled'] if enabled and self.can_translate(selection[0]) else ['disabled'])
        self.title_again_button.state(['!disabled'] if selection and not self.title_running and needs_title(self.mods[selection[0]], {}) else ['disabled'])
        if not selection:
            self.detail_name.set('Ready when you are')
            self.detail_original.set('')
            self.detail_meta.set('Choose a mod to view its saved progress and translation options.')
            self.detail_saved.set('')
            self.detail_image.configure(image='', text='Select a mod')
            return
        ident = selection[0]
        mod = self.mods[ident]
        name = mod.get('title') or mod['name']
        self.detail_name.set(name if len(name) <= 85 else name[:82] + '…')
        original = mod['name'] if mod.get('title') else ''
        self.detail_original.set(original if len(original) <= 60 else original[:57] + '…')
        self.detail_meta.set(' · '.join(str(mod[key]) for key in ('origin', 'author', 'version') if mod.get(key)))
        from saved_translations import note
        self.detail_saved.set(note(self.saved.get(ident)) or 'No saved translation yet')
        image = self.detail_photos.get(ident)
        self.detail_image.configure(image=image or '', text='' if image else 'No preview available')

    def retranslate_selected(self):
        if self.busy or not self.list.selection():
            return
        if messagebox.askyesno('Translate mod again',
                'Translate every entry again using your selected API key, parallel requests and batch size?\n\n'
                'This makes new requests using your selected translation mode. A backup of your previous translations will be saved.', parent=self):
            self.translate(retranslate=True)

    def retranslate_title(self):
        if self.title_running or not self.list.selection():
            return
        self.start_titles([self.mods[self.list.selection()[0]]], retranslate=True)

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
            note = 'Choose Google Translate in Translation models, or add your own OpenRouter API key.'
        elif self.balance_profile.get('keyless'):
            note = 'Google Translate · no API key · experimental web service · throttling may occur.'
        elif self.balance_profile.get('free_only'):
            note = f'Free OpenRouter models · intelligence ≥ {self.balance_profile["minimum_intelligence"]:g} · daily quotas apply · no paid fallback.'
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
        if self.balance_profile.get('keyless'):
            self.balance_label.set('Google Translate · 0p')
            self.balance_detail.set('No API key · experimental')
            return
        if self.balance_profile.get('free_only'):
            self.balance_label.set('Free translation · 0p')
            self.balance_detail.set('OpenRouter request quotas apply')
            return
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
        self.refresh()
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
        if self.busy or self.scanning_mods:
            return
        if not self.game:
            self.status.set('Install Tale of Immortal in Steam, then click Retry setup. If it is already installed, choose its folder.')
            self.choose.pack(before=self.action, fill='x', pady=10)
            self.setup_retry.pack(before=self.action, fill='x', pady=5)
            self.steam_install.pack(before=self.action, fill='x', pady=5)
            return
        # Browsing downloaded mods does not require a working game runtime.
        self.scanning_mods = True
        def scan():
            try:
                mods = discover(self.game)
                from destinies import destiny_mod
                mods.append(destiny_mod(self.game))
                statuses = scan_statuses(mods)
            except Exception:
                self.events.put(('mods_error', 'Could not read your mods. Choose the game folder from Options.'))
                return
            self.events.put(('mods', (mods, statuses)))
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

    def refresh_saved(self):
        """Re-read the saved mod projects in the background to update the ticks."""
        mods = list(self.mods.values())
        if not mods:
            return
        def job():
            try:
                self.events.put(('saved', scan_statuses(mods)))
            except Exception:
                pass
        threading.Thread(target=job, daemon=True).start()

    def start_titles(self, mods=None, retranslate=False):
        """Translate unknown Chinese mod names once, then keep them for later launches."""
        mods = list(self.mods.values()) if mods is None else mods
        if self.title_running:
            self.title_refresh_pending = True
            return
        self.title_refresh_pending = False
        if not retranslate:
            from shared_library import reuse_titles
            from mod_titles import save_titles
            if reuse_titles(mods, self.titles):
                save_titles(self.titles)
                apply_titles(list(self.mods.values()), self.titles)
                self.render()
        if not any(needs_title(mod, {} if retranslate else self.titles) for mod in mods):
            return
        self.title_running = True
        self.title_refresh_pending = False
        self.title_stop.clear()
        def job():
            titles = load_titles()
            try:
                result = translate_titles(mods, titles, stop=self.title_stop.is_set,
                                          progress=lambda message: self.events.put(('title_progress', message)),
                                          on_save=lambda value: self.events.put(('titles', value)),
                                          retranslate=retranslate)
            except Exception as exc:
                result = {'translated': 0, 'failed': 0, 'saved': len(titles), 'error': str(exc), 'cancelled': False}
            self.events.put(('titles_done', result))
        threading.Thread(target=job, daemon=True).start()

    def cost_columns(self, ident):
        from destinies import PROJECT_ID
        estimate = self.estimates.get(ident)
        text = 'Calculating…' if estimate is None else ('Unavailable' if estimate.get('error') else format_pence(estimate))
        if ident == PROJECT_ID:
            access = 'Always available'
        elif not self.friends or self.personal_key or self.balance_profile.get('free_only'):
            access = 'Available'
        elif estimate is None:
            access = 'Checking cost…'
        elif estimate.get('error') or not estimate.get('complete'):
            access = 'Estimate unavailable'
        else:
            access = 'Available' if full_translation_allowed(estimate) else 'Over 5p limit'
        if self.saved.get(ident, {}) and self.saved[ident].get('complete'):
            access = '✓ Translated'
        return text, access

    def can_translate(self, ident):
        from destinies import PROJECT_ID
        from shared_library import library_key, load_index
        shared = library_key(self.mods.get(ident, {})) in load_index().get('mods', {})
        return ident == PROJECT_ID or not self.friends or self.personal_key or self.balance_profile.get('free_only') or shared or full_translation_allowed(self.estimates.get(ident))

    def render(self):
        selected = self.list.selection()
        self.list.delete(*self.list.get_children())
        term = self.search.get().casefold()
        for ident, mod in self.mods.items():
            label = display_name(mod, self.titles)
            if term in (mod['name'] + ' ' + label + ' ' + ident).casefold():
                # A tick marks a mod that already holds a complete saved translation.
                self.list.insert('', 'end', iid=ident, text=tick(self.saved.get(ident)) + label,
                                 values=self.cost_columns(ident), image=self.thumbnails.get(ident) or '')
        if selected and self.list.exists(selected[0]):
            self.list.selection_set(selected[0])
        self.library_count.set(f'{len(self.list.get_children())} mods')
        self.selected()

    def selected(self, _=None):
        self.update_bulk_controls()
        self.update_detail()
        if self.busy:
            return
        selection = self.list.selection()
        self.action.state(['!disabled'] if self.setup_ready and selection and self.can_translate(selection[0]) else ['disabled'])
        if not self.setup_ready:
            # Keep the setup failure and its recovery instructions visible while browsing.
            return
        if selection:
            self.folder = APP / 'projects' / selection[0]
            if selection[0] != self.current_selection:
                mod = self.mods[selection[0]]
                saved = self.saved.get(selection[0])
                if saved and saved.get('complete'):
                    self.status.set(tick(saved) + display_name(mod, self.titles) +
                                    ' already has a full saved translation. Existing text is reused.')
                else:
                    self.status.set('Ready to translate ' + display_name(mod, self.titles))
            if not self.can_translate(selection[0]):
                self.status.set(self.cost_columns(selection[0])[1] + '. Destiny-menu translation and installing saved translations remain available.')
            self.current_selection = selection[0]
        else:
            self.current_selection = None

    def translate(self, retranslate=False):
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
                if not retranslate:
                    self.prepare_shared_mod(mod)
                result = run_job(mod, self.folder, lambda message: self.events.put(('progress', message)), self.stop.is_set,
                                 game=self.game, concurrency=concurrency, batch_size=batch_size, retranslate=retranslate)
                self.events.put(('result', (mod['id'], result)))
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
                                  self.stop.is_set, game=game, concurrency=concurrency, batch_size=batch_size,
                                  prepare_mod=self.prepare_shared_mod)
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
                self.refresh_saved()
                continue
            if kind == 'update_progress':
                self.update_status.set(value)
                continue
            if kind == 'update_error':
                self.update_running = False
                self.update_button.state(['!disabled'])
                self.update_status.set('Updates: ' + value)
                continue
            if kind == 'update_checked':
                self.update_running = False
                update, manual = value
                self.available_update = update
                if update:
                    self.update_status.set(f'Version {update["version"]} is available. Install it when you are ready.')
                    self.update_button.pack(side='right')
                elif manual:
                    self.update_status.set('You have the latest version.')
                continue
            if kind == 'update_prepared':
                self.prepared_update = value
                self.finish_update()
                continue
            if kind == 'shared_done':
                self.shared_running = False
                if value:
                    self.update_status.set('Shared library: ' + value)
                self.start_titles()
                continue
            if kind == 'mods':
                self.scanning_mods = False
                mods, statuses = value
                self.mods = {m['id']: m for m in mods}
                apply_titles(list(self.mods.values()), self.titles)
                self.saved = statuses
                self.refresh_thumbnails()
                self.refresh_estimates()
                self.refresh_shared()
                if self.setup_ready and not self.busy:
                    self.status.set('Click a mod to get started.' if mods else 'No downloaded mods found. Subscribe to a mod in Steam Workshop, then refresh.')
            elif kind == 'mods_error':
                self.scanning_mods = False
                self.title_status.set(value)
            elif kind == 'title_progress':
                self.title_status.set(value)
            elif kind == 'titles':
                # Saved titles arrive one batch at a time; the list updates in place.
                self.titles = value
                apply_titles(list(self.mods.values()), self.titles)
                self.render()
            elif kind == 'titles_done':
                self.title_running = False
                if value.get('error'):
                    self.title_status.set('Mod titles could not be translated: ' + value['error'] + ' Retry with Options → Refresh mods.')
                elif value.get('failed'):
                    self.title_status.set('Some mod titles still need translation. Retry with Options → Refresh mods.')
                else:
                    self.title_status.set('')
                self.update_detail()
                if self.title_refresh_pending:
                    self.start_titles()
            elif kind == 'saved':
                self.saved = value
                self.render()
            elif kind == 'result':
                ident, result = value
                self.saved[ident] = job_status(ident, result)
                self.finish()
                self.render()
                state = result['state']
                if state == 'success':
                    installed = result.get('installation')
                    if installed:
                        self.status.set(installation_message(installed))
                    else:
                        self.status.set('Translations saved, but installation did not complete. Use Options → Install saved translations.')
                elif state == 'empty':
                    self.status.set('No readable Chinese text was found. You can check the coverage report in the saved files.')
                elif state == 'cancelled':
                    self.status.set('Cancelled. Saved progress will be reused next time.')
                else:
                    installed = result.get('installation')
                    if installed:
                        self.status.set(installation_message(installed, partial=True))
                    else:
                        self.status.set(f'{result["count"]:,} translations saved. Some text still needs review; see the saved files.')
                self.result_button.pack(before=self.action, pady=(10, 0))
            elif kind == 'error':
                self.finish()
                self.status.set(value)
                self.refresh_saved()
            elif kind == 'destinies':
                self.finish()
                mod, report, changed = value
                self.mods[mod['id']] = mod
                apply_titles([mod], self.titles)
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
                self.refresh_saved()
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
            self.refresh_saved()
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
        if self.update_running and self.prepared_update is None:
            self.update_stop.set()
        self.title_stop.set()
        if self.collecting_logs:
            self.log_status.set('Finishing log collection. Close again when done.')
            return
        if self.busy:
            self.stop.set()
            self.status.set('Stopping setup safely. Close again when stopped.' if self.setting_up else 'Waiting for requests already sent to finish and save. Close again when stopped.')
            return
        if self.title_running:
            self.title_status.set('Finishing the title request and saving it. Close again when it has stopped.')
            return
        self.estimate_stop.set()
        self.title_stop.set()
        self.destroy()

    def destroy(self):
        # Cancel Tk callbacks when this window closes, including in GUI tests
        # that open another window in the same interpreter.
        try:
            for callback in self.tk.call('after', 'info'):
                self.after_cancel(callback)
        except tk.TclError:
            pass
        super().destroy()
