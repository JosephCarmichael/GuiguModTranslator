# Guigu Mod Translator

**Choose a mod → Translate and install → restart the game and play.**

Double-click `GuiguModTranslator.exe`. The Windows executable includes Python,
Tk, the mod readers and all required packages. Your friends do not need Python,
pip, another translation app or an API-key setup step.

The friends package is `release/GuiguModTranslator-Friends.zip`, or the timestamped
Friends ZIP from a side-by-side build. Send the **Friends** ZIP, not the Personal one.
They extract it and open `GuiguModTranslator.exe` or `Launch.bat`. It requires
64-bit Windows 10/11, an internet connection and downloaded Tale of Immortal mods.
The included shared access calls DeepSeek V4.1 Flash through OpenRouter.

Each mod has a **Full-mod estimate** column, in pence. In the friends edition,
full translation is unavailable when that estimate exceeds **0.5p (£0.005)**.
The personal edition shows estimates without this restriction. The **Translate
destiny menu** button is available in both editions and is exempt from the limit.
It translates the separate character-creation destiny project, not the full mods
that supply those destinies. Installing saved translations remains available.

Estimates scan source files locally without translation requests or changes to saved
projects. They include all extracted nontechnical source text, even if already
translated, plus request overhead and a 30% allowance. Peak Flash 4.1 rates and an
ECB exchange-rate snapshot provide the GBP conversion. These are estimates, not
guaranteed bills. See **Options → About cost estimates** for dates and assumptions.
Unreadable or partial source files mark the estimate incomplete and keep full
translation unavailable in the friends edition. Refresh mods after source changes.

The app detects Steam libraries automatically. If needed, use **Options →
Choose game folder** once. Select a mod, then press **Translate and install**.
Extraction and translation run together. The same button cancels a running job.
Progress is saved after each batch, and existing translations survive rescans.

**Max parallel requests** sets the ceiling for simultaneous DeepSeek batches:
**1, 4, 8, 16, 32, 64 or 128**, with **16** as the default. The app remembers your
choice. **Entries per request** selects **12, 24, 48 or 96** entries; the default is
**48**. The app retains a 6,000-character batch target and keeps each entry intact.
If a response reaches the output limit, the app splits that batch into smaller
batches and retries them. An individual entry that still exceeds the output limit
is kept untranslated for review while the rest continues. The progress display shows
completed translations and pending requests. Higher settings can improve speed
when the service has capacity; they do not guarantee proportional speedups.

Completed batches are matched to their original text and saved by one coordinator,
including when replies arrive out of order. Simultaneous completions share a
checkpoint. Rate limits and temporary provider errors automatically reduce actual HTTP
concurrency, pause new attempts across the job, and stagger retries. The progress
display shows the actual limit, HTTP error code and retry countdown. After a stable
run of successful requests, capacity recovers gradually up to your chosen ceiling.
The app honors `Retry-After`, otherwise waits 5, 10, 20, 40, then 60 seconds plus
jitter, with up to eight attempts per batch. Authentication, insufficient credit,
and access-denied errors stop immediately with their actual HTTP codes. Cancellation stops dispatching
new work and saves successful replies from requests already sent; those requests
must finish or time out before the job closes. Retries and account errors keep
completed translations available for resuming. Persistent outages can still stop
a job after the retry budget; the app cannot remove provider-side limits.
`request-errors.jsonl` in the saved project records provider, model, error codes,
retry delays and reduced concurrency, without keys or submitted text.

The app installs `Mods/GuiguModTranslation.dll` and the selected mod's validated
translations into `UserData/GuiguModTranslator/installed.json`. **Restart the game
after installation, updates or removal.** Your next game process loads the
translations and replaces matching displayed Chinese text with English.
Incomplete translations remain labelled as needing review; valid entries can
still be installed. Connection failures preserve saved translation progress.

Already translated a mod? Select it and choose **Options → Install saved
translations**. This also applies edits made in the translation editor without
another paid translation request. **Options → Remove selected mod’s translations**
removes that mod's installed dictionary while keeping your saved project.

The runtime targets the game's bundled **MelonLoader 0.5.x / Unhollower** runtime.
Launch the game once before installation so its managed assemblies exist. The
installer checks dependencies and the bundled loader's integrity before starting
translation. It reports missing or incompatible dependencies instead of claiming
installation succeeded. If Windows has locked the loader, close the game and
use **Install saved translations** again.

The detailed editor, CSV import/export and coverage report are under **Options →
Translation editor**. They are kept off the main translation screen.

**Find untranslated destinies** checks starting-destiny names, hover tips and
introductory descriptions across downloaded mod tables and the game's latest
loaded inventory. It selects **Character creation destinies**; press **Translate
and install** to fill its missing text. Existing valid English and saved edits
are reused. Partly Chinese translations and broken formatting stay pending.
The scan itself makes no translation requests.

The button also installs the destiny detector. Restart the game after the first
update, open character creation, and scan again. The detector inventories every
loaded type-1 destiny, including ones not rolled or hovered, and records Chinese
text encountered in destiny/tooltip UI while character creation is open. Hover
tooltips to capture additional dynamically assembled text. Destiny localisation
is translated before tooltip formatting; empty English entries can fall back to
authored Chinese for translation. Missing localisation rows remain reported.

The saved `character-creation-destinies/untranslated-destinies.json` report lists
missing fields and unresolved keys. `UserData/GuiguModTranslator/destiny-inventory.json`
records the runtime process ID and capture time. Downloaded tables can include
inactive mods; runtime data reflects its last game session. These are inventories,
not a claim that every tooltip has been visually checked. Restart after installing
translations to refresh the game's dictionary.

Packaged copies save work under `%LOCALAPPDATA%\GuiguModTranslator`. The source
version uses its own folder. Existing local credentials can be stored in
`service.json`; builds include only the explicitly configured shared profile.
No projects, game files, saves or personal credentials are included in the ZIP.

## What gets extracted

- Game-encoded `ModExportData.cache`, `ModData.cache`, `ModProject.cache` and
  loose `ModExcel/**/*.json`, including comments and trailing commas.
- All Chinese string values across localisation and gameplay tables:
  item names/descriptions, skill and trait tooltips, dialogue, choices,
  quests, logs, NPC text and mod descriptions. Referenced localisation keys
  are linked back to their table rows when present in the selected mod.
- JSON embedded in JSON strings; CSV/TSV; YAML; XML/HTML; ordinary text and
  config; source-code string literals; Unity prefab text; Excel cells.
- .NET DLL user-string heaps and string resources, including compiled mod
  output folders. Assemblies are inspected without executing their code.
- Unity bundle TextAssets and MonoBehaviour fields with readable type trees.

Every occurrence keeps a file and field/cell/object location. Identical text
is deduplicated exactly, preserving whitespace, line breaks and formatting.
Chinese-containing identifiers are retained for review rather than silently
discarded. **Player text** is a field-based classification, not proof that a
string appears in a particular gameplay path. **Review candidates** include
code literals, editor labels and diagnostics. **Technical** entries include
asset names/paths and dispatch identifiers and are excluded from translation.

Unity tags and common substitution tokens are masked before machine
translation and verified afterwards. CSV import rejects changed tokens,
changed source/IDs, and conflicting duplicate rows before applying any edits.
CSV retains exact source text; import its columns as text in spreadsheet
software to avoid automatic formula or number conversion.

## Coverage limits

The included runtime translates Unity UI `Text`, TextMeshPro text properties
and string `SetText` overloads, and `TextMesh`. A periodic scan also handles
active prefab labels and text set through other paths. Matching is exact; common
numbered `{0}` templates also match after the game substitutes values. Rich-text
tags and placeholders remain intact.

Complete text runs separated by supported rich-text tags or line breaks also
match, preserving their surrounding whitespace and formatting. Known names are
never substituted inside longer Chinese words.

Translations affect display components globally: identical Chinese text may also
appear in another mod or the base game. Conflicting translations across installed
mods resolve automatically: the most recently installed dictionary takes priority.
The other dictionaries keep their own translations, so removing the newer one
restores the previous wording. Reinstalling a dictionary gives it priority again.
Within a project, manual edits win over existing mod translations, then machine
output; stable entry IDs break ties. Invalid formatting and entries needing review
are still excluded. Ambiguous formatted matches remain unchanged. Translations
remain active until removed in this app, even if a source mod is disabled in the
game. Dictionaries whose source path no longer exists are skipped at startup.
Custom renderers, text baked into images, and dynamically combined text without
a matching template may remain Chinese. `%s`, named placeholders, and advanced
format specifiers only work when the exact source reaches the display hook.
No claim is made that every screen of every mod has been verified.

The installer writes only its own loader and dictionary files. Original mod
bundles, compiled DLLs, game binaries and saves remain unchanged. Updates and
removals save the previous dictionary under `UserData/GuiguModTranslator/backups`.
The shared runtime DLL remains installed after removing a dictionary and is inert
when no translations remain. Projects and translation exports stay separate from
the installed dictionaries. Installing changes takes an app-specific lock;
a crashed installation may leave `installed.lock`, which can be removed once all
translator processes have closed.

No static extractor can promise every player-visible string: text painted
into images, speech without subtitles, dynamically assembled text, obfuscated
or encrypted code strings, and Unity behaviours without type information
need visual/OCR work or runtime capture. Files and objects needing that work
are explicitly listed in **View coverage report** and `coverage.json`.
Media files are inventoried but no OCR or speech recognition runs. Unity
textures are identified in bundle object counts, not OCRed. Large external
Unity resource streams and media references may require additional review.

Source/editor and exported copies can differ; the scan includes both, and
keeps provenance. This deliberately favours finding text over claiming that
every candidate is active in the installed build. Build intermediates and
Unity editor/package directories are skipped. User-generated text and base
game strings referenced by a mod are outside that mod's extraction.

## Output

`projects/<mod ID>/` contains:

- `project.json`: source units, translations, provenance and coverage.
- `strings.csv` / `strings.json`: translation exports.
- `dictionary.json`: available translations keyed by exact source text.
- `coverage.json`: per-file hashes, statuses, asset object counts and gaps.

`UserData/GuiguModTranslator/runtime-status.json` in the game folder reports the
running loader's version, process ID, loaded dictionary hash, entry and replacement
counts, installed hooks and errors. It is refreshed while the game runs; compare
the process ID with the current game process before treating it as live evidence.

`projects/inventory.json` records downloaded Workshop and local loader mods.
`AUDIT.md` records the extraction/validation performed on this installation.

## Developer commands

The release has no Python requirement. To work on source code, use Windows Python
3.13, install `requirements.txt`, then run `entry.py`. The loader build also
requires the .NET SDK and .NET Framework 4.7.2 targeting pack. Set up the ignored
`bundled_service.json` with your authorized shared `api_key` before packaging;
`service.json` is for personal local access. Neither credentials nor binaries
are stored in the source repository. Build with PyInstaller:

```bat
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.venv\Scripts\python.exe -X utf8 build_release.py
.venv\Scripts\python.exe -X utf8 build_release.py --offline --side-by-side --edition friends
.venv\Scripts\python.exe -X utf8 build_release.py --offline --side-by-side --edition personal
```

The build compiles and tests the runtime loader, then verifies a folder bundle, then creates and tests the single-file
executable in an isolated folder, and finally assembles the friends ZIP. Source
CLI commands remain available through `python entry.py`; the main window opens
with no arguments, and `--advanced` opens the detailed editor.

The edition is embedded at build time, not selected in user preferences. Builds
default to Friends. The shared translation entry point enforces the limit for
the main window, editor and CLI before requests are sent. A frozen app with
missing or invalid edition metadata retains the Friends restriction.

[Cost estimates and friends-limit validation](COST_ESTIMATE_VALIDATION.md)
documents the calculation, pricing sources, packaging and checks.

## Implementation references

The installed game's `EncryptTool.EncryptMult` and `GameConf` were inspected
locally to verify the repeating-byte mod encoding; no mod code is executed.
The bundled `EncryptTexture.cs` example confirms the 21-byte format marker.
The implementation currently targets that format, and reports unknown
formats instead of guessing a successful decode.

Binary inspection uses [UnityPy](https://github.com/K0lb3/UnityPy) and
[dnfile](https://github.com/malwarefrank/dnfile). The standalone translation client handles
batching, retries and formatting protection.

DeepSeek's [V4.1 Flash release announcement](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)
specifies `deepseek-flash` as the API model name.

## Installation CLI

```bat
.venv\Scripts\python.exe entry.py --game "C:\path\to\game" install projects\2859071194
.venv\Scripts\python.exe entry.py --game "C:\path\to\game" installed
.venv\Scripts\python.exe entry.py --game "C:\path\to\game" uninstall 2859071194
```

The `translate` CLI command still saves a project; run `install` afterwards.
Add `--concurrency 32` (or another listed value) to override the saved request limit
for that translation run, for example `entry.py translate projects/2859071194 --concurrency 64`.

`entry.py scan-destinies --install-detector` performs the destiny audit and installs
the runtime detector. Omit `--install-detector` for a scan without installation.
Translate the resulting `projects/character-creation-destinies` project, then
install it using the same commands as other projects.
The main desktop button runs both steps. Installation conflicts resolve automatically
and the success message reports their count. If a previous installation stopped on
a conflict, choose **Options → Install saved translations** to retry without API calls.

The runtime uses [Harmony prefix patches](https://harmony.pardeike.net/v2/articles/patching-injections.html)
to substitute the text argument before Unity displays it. Build references come
from the local game's assemblies; no proprietary game DLLs are redistributed.

[Parallel-request implementation and validation](PARALLEL_TRANSLATION_VALIDATION.md) records the concurrency and live API checks.

[Provider throttling diagnosis and recovery validation](PROVIDER_RECOVERY_VALIDATION.md) records the reproduced direct-DeepSeek HTTP 429 errors and the fix.

Changing provider or batch size preserves the saved translations. The main button
rescans source files, reuses matching translations, and sends only untranslated
entries. The progress display includes the total already saved. Translation model
metadata is also preserved on rescans.

For example: `entry.py translate projects/2814696167 --include-review --concurrency 16 --batch-size 48`.
Build an isolated update without paid test requests or replacing current app files
with `build_release.py --offline --side-by-side`.

[Larger batches and resume validation](BATCH_SIZE_VALIDATION.md) records the
provider-switch checks and fixes for narration and percentage validation.

[Automatic conflict resolution validation](CONFLICT_RESOLUTION_VALIDATION.md)
records installation priority, reversible removal and runtime checks.
