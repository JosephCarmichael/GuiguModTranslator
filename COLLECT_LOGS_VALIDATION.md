# Collect logs — 1.3.1

The main Friends EXE has a Collect logs button and an Options menu entry. They
remain available during setup, translation or failure. Collection runs in a
separate worker and does not cancel or reset the active job. The footer reports
completion independently of setup progress.

One click writes Guigu-Logs.txt beside the executable (APP_DIR, not PyInstaller's
extraction directory) and copies the text as Unicode to the Windows clipboard.
A native clipboard owner avoids Tk clearing the data when its window closes.
If the EXE folder is read-only, copying still works. If the clipboard is busy,
the saved file still works. Only if both destinations fail does the app offer
another save location. No diagnostic ZIP or external script is produced.

The report includes live app state, Windows code page, native runtime checks,
relevant file hashes, current and three recent loader logs, Player logs, relevant
Windows Application events and filtered Steam launch lines. Original source file
times distinguish stale shipped logs from recent launches. Logs are bounded to
128 KiB each, explicitly marked when truncated. Saved translations, API profiles
and saves are excluded. Credential-like tokens in the collected text are redacted.

Validation:

- Six targeted unit tests passed: Unicode/live state, missing files, credential
  exclusion/redaction, bounded tails, same-folder text plus clipboard, read-only
  folder fallback and clipboard-busy fallback (combined cases).
- Real Windows GUI collection passed at the minimum 650x650 window size while
  simulating stuck setup. The setup state and cancellation flag were unchanged.
- The report included actual Windows event collection and code-page inspection.
- Saved text and clipboard contents matched. A new Tk window could still read
  the complete report after the original app window closed.
- The final one-file build is checked from a copied isolated folder without
  Python on PATH, including actual native clipboard persistence after closure.

Evidence: evidence/collect-logs-gui-check.json, evidence/collect-logs-button.png,
and projects/log-button-final-onefile-check.json.
