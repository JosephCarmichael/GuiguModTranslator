# Guigu Mod Translator

Translate Chinese **Tale of Immortal** mods into English, install the results,
and reuse saved community translations.

[Download for Windows](https://github.com/JosephCarmichael/GuiguModTranslator/releases/latest) ·
[User guide](docs/USER_GUIDE.md) · [Development](docs/DEVELOPMENT.md)

**No API keys are included in the download.** The repository is currently private;
downloads still require repository access.

## Get started

1. Install Tale of Immortal through Steam and download your mods.
2. Download **GuiguModTranslator-Public.zip**, extract it outside the game folder,
   and open **GuiguModTranslator.exe**.
3. Let automatic setup finish. Choose a provider under **Translation models…**.
4. Select a mod, choose **Translate and install**, then restart the game.

Requires **64-bit Windows 10/11** and internet for new translations and downloads.
Python is included. First-time setup may request Windows permission or a restart.

## Translation options

| Option | Setup | Cost and limits |
| --- | --- | --- |
| **Google Translate (experimental)** | None; default for new public installs | No key or API charge. Uses an unofficial web integration; Google may throttle or change it. |
| **OpenRouter Free** | Your own OpenRouter key | Zero-price models with account-wide request quotas. |
| **OpenRouter Paid** | Your own OpenRouter key and credit | Pay for new translations; estimates appear beside each mod. |

OpenRouter Free normally allows **50 requests/day**, or **1,000/day** after at
least **$10 in lifetime credit purchases**, with a **20/minute** limit.
Retries and title translations count toward the account's allowance.
[OpenRouter limits](https://openrouter.ai/docs/api/reference/limits).

Google requests run one at a time. Throttling stops the job and preserves saved
progress for resuming. Providers never switch automatically to a paid option.
Your OpenRouter key is stored encrypted for your Windows account.

## Features and saved work

- Mod text, English titles, character-creation destinies, and bulk translation.
- Saved progress, an editor, CSV import/export, and reusable shared translations.
- Startup checks for newer GitHub releases; installation is optional.
- Updates preserve work in `%LOCALAPPDATA%\GuiguModTranslator`.

The app downloads the published shared library and includes an offline snapshot.
**It does not automatically upload or back up your projects online.**
Saved translations cost nothing to reuse. Back up your local data folder.

Original mod files and game saves are preserved. Text in images, custom
renderers, or unmatched dynamic text may remain Chinese.
For help, use **Collect logs** or see the [user guide](docs/USER_GUIDE.md).
