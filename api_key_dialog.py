"""Personal OpenRouter key settings for the portable desktop app."""
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from api_access import save_openrouter_key, use_shared_key, using_personal_key

OPENROUTER_HELP = (
    'An API key connects this app to OpenRouter, which provides the AI translations.\n\n'
    '1. Sign up to OpenRouter at openrouter.ai.\n'
    '2. Open Settings → API Keys and click “New API key” (or “Create key”).\n'
    '3. Add a little credit to your account — a few pounds’ worth to start.\n'
    '   OpenRouter takes payments in US dollars.\n'
    '4. Copy the key, paste it into the box here, and click “Save personal key”.\n\n'
    'Your own key lets you translate full mods without the app’s cost cap.\n'
    'Translations are usually cheap; check the estimate beside each mod.\n\n'
    'You don’t need to pay to translate the same text again! Saved translations\n'
    'don’t expire and keep working without API credit. Keep your saved translation\n'
    'files — new or changed text in a mod update may still need translating.\n\n'
    '“Insufficient funds” on the shared key means the shared credit or spending\n'
    'allowance has run out — the 50p key I gave you has run dry :(.\n'
    'Add your own key to keep translating. If you’re already using your own key,\n'
    'top up your OpenRouter account or check the key’s spending limit.\n\n'
    'Your existing translations will still work.'
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
        ttk.Label(body, text='Personal-key translations use your OpenRouter credit and have no app cost cap.\n'
                  'The shared key keeps its existing translation-cost limit.', wraplength=470).pack(anchor='w', pady=(10, 12))
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
        self.shared_button = ttk.Button(buttons, text='Use shared key', command=self.shared)
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
        self.changed('Personal OpenRouter key saved. Translations will use your credit, with no app cost cap.')
        self.close()

    def shared(self):
        try:
            use_shared_key()
        except (OSError, ValueError) as exc:
            self.message.set(str(exc))
            return
        self.changed('Switched to the shared key. Its translation-cost limit is active again.')
        self.close()

    def close(self):
        self.key.set('')
        self.destroy()
