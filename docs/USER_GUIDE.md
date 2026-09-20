# User guide

[Back to the project](../README.md)

## Install and translate

Download the Friends ZIP from [Releases](https://github.com/JosephCarmichael/GuiguModTranslator/releases/latest),
extract it outside the game folder, and open `GuiguModTranslator.exe`.
The current repository is private; your GitHub account needs access.

The app locates Steam and installs missing MelonLoader components and the
translation plugin. First launch can take several minutes. Follow the setup bar
and approve Windows permission requests when needed. If a runtime requires a PC
restart, reopen the app afterward. Save and close an open game before setup
changes its files.

Select a mod and choose **Translate and install**. Progress is saved after each
batch. Cancel stops new requests and saves successful requests already running.
Restart the game after installing, updating, or removing translations.

If detection fails, use **Options → Choose game folder**. **Retry setup** resumes
interrupted setup. **Collect logs** copies a diagnostic report and saves
`Guigu-Logs.txt` beside the app; review the report before sharing it.

## Translation keys and limits

Use **API key… → Save personal key** to use your own OpenRouter account.
The key is encrypted for your Windows account and stored locally. Saving validates
its format; the first request checks access and credit. Personal-key errors do
not switch to the shared account. **Use shared key** removes the personal key.

In the Friends edition, the shared key permits full-mod estimates up to
**5p (£0.05)**. A personal key removes that app restriction. The separate
**Translate destiny menu** project is exempt from the shared-key cost cap.

Estimates include the full extracted mod, even text already saved. Actual
charges depend on requests made. Incomplete estimates block full-mod translation
with the Friends shared key. **Options → About cost estimates** explains the
calculation.

The **Free** model option is not in the published v1.4.0 executable. OpenRouter's
free-model quota belongs to the account: normally 50 requests per UTC day, or
1,000 after at least $10 in lifetime credit purchases, with 20 requests/minute.
Retries and title translations also use requests. Rotating models does not create
a separate daily allowance. See [current limits](https://openrouter.ai/docs/api/reference/limits).

## Saved work and shared translations

Portable builds save projects, settings, and titles in
`%LOCALAPPDATA%\GuiguModTranslator`. Back up that folder to protect your work.
Replacing the EXE or installing an update preserves it. Source checkouts use
their own folder unless `GUIGU_TRANSLATOR_DATA` is set.

The app refreshes the shared library from GitHub and checks downloaded file
hashes. Matching source text is reused without translation requests; local
translations and edits take priority. A bundled snapshot remains usable offline.
Changed or missing text still needs translation.

The library does not provide automatic cloud backup or two-way project sync.
The maintainer exports and publishes reviewed entries. Users' projects are not
automatically uploaded.

Choose **Options → Install saved translations** to apply existing work or editor
changes without translating again. **Translate mod again** deliberately requests
new translations using your settings and backs up the previous project.
**Title again** refreshes the selected mod's English name.

The editor under **Options** supports manual changes and CSV import/export.
Keep IDs, source text, and formatting tokens intact. Import spreadsheet columns
as text to avoid automatic conversions.

## Bulk translation and destinies

**Translate all** includes discovered mods at or below the slider's per-mod
estimate, cheapest first, regardless of the search filter. The combined cost
can exceed the slider value. The Friends shared-key cap still applies.
**Cancel all** preserves completed progress.

Use **Find untranslated destinies** to scan character-creation text, then
**Translate and install** for the selected destiny project. After first installing
the detector, restart the game and open character creation before scanning again.
Hover tooltips to capture additional dynamic text. Reports may include downloaded
mods that are not active in the current session.

## Updates and GitHub access

Version 1.4.0 and later check for newer stable releases at startup.
**Options → Check for updates** checks again. **Install update** asks before
downloading, verifies ZIP and executable checksums, then restarts the app.
Finish or cancel translation before updating. The previous executable is retained
as `GuiguModTranslator.previous.exe`.

Private releases and new library downloads require an invited GitHub account
and a token entered in **Options → GitHub access**. Give it only the access needed
to read this repository. This is separate from the translation API key.
Public repositories can be read without a GitHub token.

Older 1.3.x apps need a manual download to gain the updater.
Source checkouts are updated with Git.

## Coverage and removal

Translations replace matching displayed text. Images, unsupported renderers, and
dynamic text without a matching source or template may remain untranslated.
A completion tick describes extracted-text coverage, not a visual check of every
game screen.

Choose **Options → Remove selected mod's translations**, then restart the game.
Saved projects remain available. Dictionary backups are kept under the game's
`UserData/GuiguModTranslator/backups` folder. When installed dictionaries disagree,
the most recently installed one takes priority; removing it restores the earlier
wording.
