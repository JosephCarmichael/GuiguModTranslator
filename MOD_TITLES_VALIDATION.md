# Mod titles, translation ticks and the personal launcher — 1.3.8

Source request: `NEED-TO-ADD-TO-MY-OWN.md`.

1. **Mod titles translate automatically.** Every discovered mod whose name still
   contains Chinese is translated to English in the background, once, with the
   normal translation access. A mod that is already English, or already saved,
   costs nothing.
2. **Titles persist.** Results are written to `mod-titles.json` in the app data
   folder (`%LOCALAPPDATA%\GuiguModTranslator\` for an EXE, the app folder for
   a source run). The next launch reuses them and makes no request. A renamed
   mod is translated again, and the stale title is dropped.
3. **A tick marks finished mods.** The mod row shows `✓` when that mod
   already holds a complete saved translation. The rule is the same one the
   translation job uses for its final `success` state: every non-technical entry
   translated without `needs_review`, and no unreadable or partial source file.
   Technical identifiers are never counted. The destiny project also needs its
   runtime inventory. Selecting a ticked mod says that existing text is reused.
4. **The personal launcher runs the Personal edition.**
   `GuiguModTranslator.bat` now starts this folder's source through `entry.py`
   instead of the frozen EXE. A source run is the Personal edition, so it has
   every Friends feature with no 5p shared-key limit; the API key choice
   (bundled shared key, or your own OpenRouter key) is unchanged, and the
   Friends ZIP keeps its cap. If Python is missing, the launcher shows installation instructions and stops;
   it no longer substitutes the older Friends EXE.

How it looks: the English title and the original Chinese name share one row,
for example `Sword Sect (宝剑门)`, so the search box still matches either
language and the mod is still recognisable. Titles appear as they arrive, one
batch at a time. A provider problem, a missing key or a cancelled request leaves
the Chinese name in place and is retried on the next launch.

Files: `mod_titles.py`, `saved_translations.py`, `desktop.py`, `run.py`
(advanced editor shows saved titles), `frozen_checks.py` (two new offline
checks), `GuiguModTranslator.bat`, `tests/test_mod_titles.py`,
`tests/titles_gui_smoke.py`, `tests/simple_gui_smoke.py` (now uses a stand-in
provider so a smoke check never spends credit).

## Validation

* **164 Windows unit tests passed** with Python 3.13 in the project's own
  `.venv` (148 existing plus 16 new): `evidence/mod-titles-tests-windows.txt`.
  New coverage: saved titles are reused, a renamed mod is translated again,
  batches stay small and are saved one by one after each batch, provider errors
  and bad output (empty, unchanged or still Chinese) are never saved as titles,
  the tick needs every entry translated, `needs_review`, unreadable files,
  missing destiny runtime inventory and an empty project all block the tick, a
  damaged `project.json` cannot crash the list, and a real `run_job` run leaves a
  complete project that is then ticked.
* **Windows Tk window check passed**: `evidence/mod-titles-gui.txt` and
  `evidence/mod-titles-ui.png`. It found 19 mods, translated 14 Chinese names,
  saved the cache, showed `English title … (original Chinese)` rows, ticked a
  saved complete project, printed the "already has a full saved translation"
  status and captured the window. The check redirects the app data folder to a
  temporary folder and uses a stand-in provider, so this repository's saved
  translations were not touched and **no paid request was made**.
* **Main window regression check passed**: `tests/simple_gui_smoke.py`
  (`Simple window checks passed`) with the game setup stubbed, so the running
  game is never disturbed.
* **Self-test passed** including two new checks, *"Mod titles: one request for
  unknown Chinese names, saved once and reused with the original name (offline
  transport)"* and *"A saved, fully translated mod is ticked; a mod without a
  saved project is not ticked"*: `evidence/mod-titles-self-test.json`. This run
  was unfrozen (edition `personal`), so the shipped EXE has not been rebuilt:
  the new checks run in the self-test of the next build.
* The launcher itself was exercised: `GuiguModTranslator.bat --help` started the
  source app from the project venv and exited 0.

Note: the stray `string missing trailing flag` line in captured console output
comes from the existing `dnfile` dependency while reading managed DLLs; it is
not from this change.

## Edition note

`GuiguModTranslator.exe` was rebuilt as Personal during the follow-up repair,
including its embedded edition policy and the latest title/setup fixes. The BAT
still starts the source edition with this folder’s existing saved data and API
selection. The portable Personal ZIP uses the usual frozen-app data folder.

## Implementation review — 15 September 2026

The initial startup validation missed a real failure: `setup-last.json` reports
that launch repair cannot run while this source app is inside the Chinese game
folder. Mod discovery was gated on successful setup, leaving the list empty.
Windows resolves the `TaleOfImmortal` alias back to that same Chinese folder, so
merely selecting the alias does not repair launch.

Changes from this review:

- Discover mods independently of game setup. Keep setup errors visible when
  selecting rows, and keep translation/install actions gated on setup readiness.
- Show title progress and failures, with Refresh mods as the retry action.
- Remove the launcher's fallback to the older EXE, which lacks these changes and
  is treated as Friends. Dependency-install failures retain their error output.
- Clear previously attached titles when their source name no longer matches.
- Isolate cost-policy unit tests from the machine's saved personal credential.
  The initial run had three failures because the real personal key bypassed the
  simulated Friends cap; production API selection and policy are unchanged.

Checks: Windows source discovery finds 17 mods, plus the separate destiny row.
`GuiguModTranslator.bat --help` exits successfully through `entry.py`.
All 164 Windows unit tests pass. `tests/startup_mods_gui_smoke.py` verifies 18
visible rows while setup is pending and after it fails, persistent titles reused
without another request, visible title errors, and disabled translation controls
until setup succeeds. It uses temporary data and a fake provider, and performs
no game setup changes or paid translation requests. Screenshot:
`evidence/startup-mods-review.png` (fixture titles and errors).

Remaining real-environment limitation: game launch repair still requires running
the configured app from outside the game folder. This review does not claim
that setup or live API translation succeeded, and does not rebuild the EXE.

## Follow-up fixes — 15 September 2026

The launch limitation above is now resolved on this installation. See
`LAUNCH_REPAIR_VALIDATION.md`: Steam uses the verified Windows ASCII short name,
the game starts, and the translation runtime reports ready. All 14 Chinese titles
were translated through the real configured API and saved. Three leading author
labels needed a title-specific validation correction: translated `[English]`
labels are not runtime placeholders. `tests/personal_startup_live_smoke.py`
checks real setup readiness, Personal mode, visible rows and reuse of saved titles
without another translation request. Evidence is in `evidence/personal-startup-live.*`.

The Personal folder bundle and single-file EXE both passed their offline self-tests,
and the EXE passed real-mod extraction. The root EXE and
`release/GuiguModTranslator-Personal.zip` have been updated.
