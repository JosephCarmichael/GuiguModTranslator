"""Private-repository access for updates and shared translations."""
import tkinter as tk
import webbrowser
from tkinter import ttk

from github_client import ACCESS_FILE, REPOSITORY, save_token
from app_config import data_dir


class GitHubDialog(tk.Toplevel):
    def __init__(self, parent, changed):
        super().__init__(parent)
        self.title('GitHub access')
        self.transient(parent)
        self.resizable(False, False)
        panel = ttk.Frame(self, padding=24)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='App updates & shared translations', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='Public repositories need no login. For a private repository, your GitHub account must first be invited.\n'
                  'Use a fine-grained token with Contents: Read-only if this repository is selectable.\n'
                  'Invited collaborators may need a classic token with the repo scope instead.\n'
                  'This is separate from your translation API key.', wraplength=520).pack(anchor='w', pady=12)
        ttk.Button(panel, text='Open repository', command=lambda: webbrowser.open('https://github.com/' + REPOSITORY)).pack(anchor='w')
        ttk.Button(panel, text='Create read-only GitHub token', command=lambda: webbrowser.open(
            'https://github.com/settings/personal-access-tokens/new?name=Guigu%20Mod%20Translator&contents=read')).pack(anchor='w', pady=6)
        ttk.Button(panel, text='Create classic token for collaborator access', command=lambda: webbrowser.open(
            'https://github.com/settings/tokens/new?scopes=repo&description=Guigu%20Mod%20Translator')).pack(anchor='w', pady=6)
        token = tk.StringVar()
        ttk.Entry(panel, textvariable=token, show='•', width=65).pack(fill='x', pady=10)
        message = tk.StringVar(value='The token is encrypted for your Windows account and excluded from logs and packages.')
        ttk.Label(panel, textvariable=message, wraplength=520).pack(anchor='w', pady=6)

        def save():
            try:
                save_token(token.get())
            except (OSError, ValueError) as exc:
                message.set(str(exc))
                return
            token.set('')
            changed()
            self.destroy()

        def remove():
            (data_dir() / ACCESS_FILE).unlink(missing_ok=True)
            changed()
            self.destroy()

        actions = ttk.Frame(panel)
        actions.pack(fill='x', pady=(12, 0))
        ttk.Button(actions, text='Save GitHub access', command=save).pack(side='left')
        ttk.Button(actions, text='Remove saved access', command=remove).pack(side='left', padx=8)
        ttk.Button(actions, text='Close', command=self.destroy).pack(side='right')
