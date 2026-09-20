"""Personal OpenRouter key settings for the portable desktop app."""
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from api_access import save_openrouter_key, use_shared_key, using_personal_key, bundled_key, remove_openrouter_key

OPENROUTER_HELP = (
    'No API keys are included in the public download.\n\n'
    'For Google Translate, choose Translation models → Google Translate. '
    'This experimental web option needs no key and may be throttled.\n\n'
    'For OpenRouter, create your own account at openrouter.ai and create an API key. '
    'Paste it here and choose Save personal key. Then select OpenRouter Free or Paid '
    'in Translation models. Free models have daily account quotas. '
    'Paid models use your own credit; check the estimate before translating.\n\n'
    'Keys are encrypted for your Windows account and stay on this PC. '
    'Removing a key preserves saved translations. Saved text costs nothing to reuse.'
)


def show_openrouter_help(parent):
    messagebox.showinfo('What does this mean?', OPENROUTER_HELP, parent=parent)


def help_link(parent, owner):
    return tk.Button(parent, text='What does this mean?', command=lambda: show_openrouter_help(owner),
                     font=('Segoe UI', 9, 'underline'), fg='#385ee8', bg='#f5f6fa',
                     activeforeground='#2446c2', activebackground='#f5f6fa',
                     relief='flat', borderwidth=0, padx=0, pady=2, cursor='hand2')


class ApiKeyDialog(tk.Toplevel):
    def __init__(self, parent, changed):
        super().__init__(parent)
        self.changed = changed
        self.title('OpenRouter API key')
        self.resizable(False, False)
        self.transient(parent)
        self.key = tk.StringVar()
        self.message = tk.StringVar(value=('Your personal OpenRouter key is active.' if using_personal_key()
                                         else 'No personal OpenRouter key is active.'))
        body = ttk.Frame(self, padding=20)
        body.pack(fill='both', expand=True)
        heading = ttk.Frame(body)
        heading.pack(fill='x')
        ttk.Label(heading, text='Use your own OpenRouter key', font=('Segoe UI', 15, 'bold')).pack(side='left')
        self.help_button = help_link(heading, self)
        self.help_button.pack(side='right', padx=(14, 0))
        ttk.Label(body, text='Use your own key for free or paid OpenRouter models.\n'
                  'No API key is included in the public download.', wraplength=470).pack(anchor='w', pady=(10, 12))
        ttk.Button(body, text='Open OpenRouter key settings',
                   command=lambda: webbrowser.open('https://openrouter.ai/settings/keys')).pack(anchor='w')
        ttk.Label(body, text='Paste a new key (starts with sk-or-)').pack(anchor='w', pady=(14, 4))
        self.entry = ttk.Entry(body, textvariable=self.key, show='•', width=55)
        self.entry.pack(fill='x')
        ttk.Label(body, text='Saved keys are encrypted for your Windows account.\n'
                  'Saving a key does not make a translation request.', wraplength=470).pack(anchor='w', pady=(8, 10))
        ttk.Label(body, textvariable=self.message, wraplength=470).pack(anchor='w', pady=(0, 10))
        buttons = ttk.Frame(body)
        buttons.pack(fill='x')
        self.save_button = ttk.Button(buttons, text='Save personal key', command=self.save)
        self.save_button.pack(side='left')
        self.shared_button = ttk.Button(buttons, text='Use shared key' if bundled_key() else 'Remove saved key', command=self.shared)
        self.shared_button.pack(side='left', padx=8)
        ttk.Button(buttons, text='Cancel', command=self.close).pack(side='right')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda _: self.close())
        self.grab_set()
        self.entry.focus_set()

    def save(self):
        try:
            save_openrouter_key(self.key.get())
        except (OSError, ValueError) as exc:
            self.message.set(str(exc))
            return
        self.changed('OpenRouter key saved. Choose OpenRouter Free or Paid in Translation models to use it.')
        self.close()

    def shared(self):
        try:
            if bundled_key():
                use_shared_key()
            else:
                remove_openrouter_key()
        except (OSError, ValueError) as exc:
            self.message.set(str(exc))
            return
        self.changed('Shared key selected.' if bundled_key() else 'OpenRouter key removed. Choose Google Translate for translation without a key.')
        self.close()

    def close(self):
        self.key.set('')
        self.destroy()
