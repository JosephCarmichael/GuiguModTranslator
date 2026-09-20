# Guigu Mod Translator

Translate Chinese **Tale of Immortal** mods into English, install the results,
and reuse saved community translations.

[Download the Windows app](https://github.com/JosephCarmichael/GuiguModTranslator/releases/latest) ·
[User guide](docs/USER_GUIDE.md) · [Development](docs/DEVELOPMENT.md)

**Download status:** the repository and v1.4.0 release are currently private.
Downloads require repository access. A public package is still being prepared.

## Get started

1. Install Tale of Immortal through Steam and download your mods.
2. Download **GuiguModTranslator-Friends.zip**, extract it outside the game
   folder, and open **GuiguModTranslator.exe**.
3. Let automatic setup finish, select a mod, and choose **Translate and install**.
4. Restart the game to load the translations.

Requires **64-bit Windows 10/11** and internet for new translations and downloads.
Python is included. First-time setup may request Windows permission or a restart.

## What it does

- Translates mod text, titles, and character-creation destinies.
- Saves progress, resumes unfinished jobs, and reuses matching shared text.
- Supports bulk translation, an editor, and CSV import/export.
- Checks GitHub at startup and offers **Install update** for newer releases.
  Updates are optional and keep saved translations and settings.

## Translation access

The current Friends release includes shared translation access, with a **5p
estimated full-mod limit**. A personal OpenRouter key removes that app limit;
provider charges and account limits still apply. Saved translations cost nothing
to reuse.

**Free-model translation is not included in the v1.4.0 download.**
OpenRouter's free tier normally allows **50 requests per day**, increasing to
**1,000** after at least **$10 in lifetime credit purchases**, with a **20/minute**
limit. These are account-wide requests, including retries and title translation,
so a shared key does not give every user a separate allowance.
[OpenRouter limits](https://openrouter.ai/docs/api/reference/limits).

## Shared translations and saved work

The app downloads published translations from GitHub and includes an offline
snapshot. **It does not automatically upload or back up your projects online.**
New shared entries are reviewed and published by the maintainer.

Your work is saved in `%LOCALAPPDATA%\GuiguModTranslator`. Keep this folder when
replacing the app. The translator preserves original mod files and game saves.
Text in images, custom renderers, or unmatched dynamic text may remain Chinese.

For setup problems, use **Collect logs**. See the [user guide](docs/USER_GUIDE.md)
for API keys, private GitHub access, editing, removal, and troubleshooting.
