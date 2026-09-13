# Guigu Mod Translator

**Choose a mod → Translate with DeepSeek → translation files ready.**

Double-click `GuiguModTranslator.exe`. The Windows executable includes Python,
Tk, the mod readers and all required packages. Your friends do not need Python,
pip, another translation app or an API-key setup step.

The friends package is `release/GuiguModTranslator-Friends.zip`. Send that ZIP.
They extract it and open `GuiguModTranslator.exe` or `Launch.bat`. It requires
64-bit Windows 10/11, an internet connection and downloaded Tale of Immortal mods.
The included shared access calls DeepSeek V4.1 Flash through OpenRouter.

The app detects Steam libraries automatically. If needed, use **Options →
Choose game folder** once. Select a mod, then press **Translate with DeepSeek**.
Extraction and translation run together. The same button cancels a running job.
Progress is saved after each batch, and existing translations survive rescans.

**Success means translation files are ready; this app does not install them
in-game.** Incomplete work is labelled as needing review, not success. When a
connection fails or the shared allowance runs out, previous progress stays saved.

The detailed editor, CSV import/export and coverage report are under **Options →
Translation editor**. They are kept off the main translation screen.

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

**This is an extractor and translation editor, not an in-game translation
loader.** `dictionary.json` is an exact-source translation dictionary for
later integration. Writing it does not make the game load translations.
An in-game loader is not included. No game/mod/save files are patched.

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

`projects/inventory.json` records downloaded Workshop and local loader mods.
`AUDIT.md` records the extraction/validation performed on this installation.

## Developer commands

The release has no Python requirement. To work on source code, use Windows Python
3.13, install `requirements.txt`, then run `entry.py`. Build with PyInstaller:

```bat
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.venv\Scripts\python.exe -X utf8 build_release.py
```

The build first verifies a folder bundle, then creates and tests the single-file
executable in an isolated folder, and finally assembles the friends ZIP. Source
CLI commands remain available through `python entry.py`; the main window opens
with no arguments, and `--advanced` opens the detailed editor.

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
