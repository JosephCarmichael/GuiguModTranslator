"""Translation mode and live free-model eligibility preview."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from app_config import translation_mode, minimum_intelligence, save_preferences


class TranslationSettings(tk.Toplevel):
    def __init__(self, parent, changed=lambda: None):
        super().__init__(parent)
        self.title('Translation models')
        self.transient(parent)
        self.grab_set()
        self.parent = parent
        self.changed = changed
        self.mode = tk.StringVar(value=translation_mode())
        self.minimum = tk.StringVar(value=f'{minimum_intelligence():g}')
        self.events = queue.Queue()
        body = ttk.Frame(self, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Radiobutton(body, text='Google Translate — no API key (experimental web service)',
                        variable=self.mode, value='google').pack(anchor='w', pady=(0, 8))
        ttk.Radiobutton(body, text='OpenRouter Paid — DeepSeek V4.1 Flash (your key)', variable=self.mode, value='paid').pack(anchor='w')
        ttk.Radiobutton(body, text='OpenRouter Free — qualifying models (your key)', variable=self.mode, value='free').pack(anchor='w', pady=8)
        row = ttk.Frame(body)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Minimum intelligence index').pack(side='left')
        ttk.Spinbox(row, textvariable=self.minimum, from_=0, to=100, increment=5, width=7).pack(side='left', padx=10)
        self.preview_button = ttk.Button(row, text='Check free models', command=self.preview)
        self.preview_button.pack(side='right')
        ttk.Label(body, text='Artificial Analysis scores measure general capability, not translation quality. '
                  'Models without a score are excluded. Scores can reflect different reasoning settings. '
                  'The starting cutoff of 30 is adjustable, not a quality guarantee.\n\n'
                  'Free mode uses your selected OpenRouter key, with no paid fallback. '
                  'Batches rotate between eligible models; failed responses try another. '
                  'Requests are paced to 20/minute across this app. Account-wide daily quotas still apply '
                  '(typically 50/day without purchased credits). Progress is saved for resuming.'
                  '\n\nGoogle Translate sends text to Google without an API key. It is an unofficial web '
                  'integration: availability and limits can change. Requests run one at a time; throttling '
                  'stops the job so you can resume later. There is no automatic paid fallback.',
                  wraplength=570).pack(anchor='w', pady=8)
        self.results = tk.Text(body, height=10, width=75, wrap='word', state='disabled')
        self.results.pack(fill='both', expand=True, pady=8)
        ttk.Button(body, text='Save settings', command=self.save).pack(side='right')
        self.poll_job = parent.after(100, self.poll)

    def cutoff(self):
        try:
            value = float(self.minimum.get())
            if 0 <= value <= 100:
                return value
        except ValueError:
            pass
        raise ValueError('Choose a minimum intelligence score between 0 and 100.')

    def show(self, text):
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.insert('end', text)
        self.results.configure(state='disabled')

    def preview(self):
        try:
            minimum = self.cutoff()
        except ValueError as exc:
            messagebox.showerror('Intelligence cutoff', str(exc), parent=self)
            return
        self.preview_button.state(['disabled'])
        self.show('Checking current zero-price models and intelligence scores…')
        def work():
            from free_models import discover
            try:
                models = discover(minimum, refresh=True)
                text = f'{len(models)} qualifying models at cutoff {minimum:g}:\n\n' + '\n'.join(
                    f'{m["intelligence"]:g}  —  {m["name"]}\n    {m["id"]}' for m in models)
            except Exception as exc:
                text = str(exc)
            self.events.put(text)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            self.show(self.events.get_nowait())
            self.preview_button.state(['!disabled'])
        except queue.Empty:
            pass
        self.poll_job = self.parent.after(100, self.poll)

    def destroy(self):
        if getattr(self, 'poll_job', None):
            self.parent.after_cancel(self.poll_job)
            self.poll_job = None
        super().destroy()

    def save(self):
        try:
            minimum = self.cutoff()
            if self.mode.get() == 'free':
                from app_config import service_profile
                service_profile(mode='free', minimum=minimum)
            save_preferences(translation_mode=self.mode.get(), minimum_intelligence=minimum)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Translation settings', str(exc), parent=self)
            return
        self.changed()
        self.destroy()
