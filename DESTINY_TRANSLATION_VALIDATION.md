# Destiny detection and translation — 2026-09-13

## Confirmed correction in 1.2.3

The user confirmed the repaired destiny text works. The live 1.2.3 process
enumerated 309 destinies and 867 fields with zero untranslated authored fields
and no loader errors. Two missing base-game localisation keys remain unresolved.
See `evidence/destiny-1.2.3-live-verified.json`.

Two runtime defects were corrected after the initial implementation: the native
generic dictionary's `TryGetValue` bridge threw `TValue_REF..ctor(intptr)`, and
Mono's `JsonDeserializer.StoreKey` called `Trim()` on translation dictionary keys.
The latter removed leading/trailing line breaks from descriptions such as
Eternally Imperishable, preventing exact matching. The detector now reads typed
localisation rows; the JSON reader protects both ends of object keys before
parsing and restores them before typed conversion. Text values and their escape
sequences remain unchanged. A replacement DataContract reader was also rejected
after a live compatibility failure; 1.2.3 uses the original reader with key
protection and adds no serialization-library dependency.

The installed dictionary passed 114 catalogue assertions inside the game's
actual embedded Mono runtime, including whitespace-sensitive keys. The app also
reports failed/stale detector inventories instead of silently treating an older
session's inventory as current. `evidence/mono-catalog-fix.txt` and
`evidence/mono-json-key-trimming.txt` record the regression checks and cause.

The earlier validation record below describes the initial implementation and
its limitations before these corrections.

The translator now has a **Find untranslated destinies** action and a dedicated
character-creation project. It scans the three starting-destiny text fields
(`name`, `tips`, `introduceText`), resolves mod localisation keys, reuses valid
English and saved edits, and reports missing translations separately from
missing source data. Negative mod IDs and zero-weight rows are included.

The runtime inventories all loaded type-1 rows over multiple frames. It also
captures untranslated text in luck/tooltip component hierarchies while character
creation is open. Destiny localisation hooks translate text before its display
formatting. Complete text runs in supported markup and multiline text can match
without substituting names inside unrelated longer words. The final loader
distinguishes intentionally empty localisation rows and falls back to authored
Chinese when a destiny's English field is empty.

Validation completed:

- 62 Python tests passed, including unresolved keys, all three text fields,
  negative IDs, zero-weight rows, partial Chinese, invalid formatting, runtime
  inventory merging, rescan preservation, cancellation and detector installation.
- 29 C# catalogue assertions passed; the loader compiled against the installed
  game's actual assemblies.
- The live detector enumerated 309 loaded destinies and 867 fields, with no
  reported loader hook errors. It captured assembled hover text missing from
  static mod extraction. See `evidence/destiny-validation.json`.
- The Windows UI scan was exercised against real mod files and runtime data in
  an isolated project. Selection, result text, restart instructions and enabled
  translation controls passed. A 650×650 window check ensures the scan button,
  action and result remain visible. See `evidence/destiny-gui-check.json` and
  `projects/destiny-scan-ui.png`.
- Existing portable folder/single-file checks and real-mod extraction checks
  passed. `tests/frozen_destiny_smoke.py` additionally runs the packaged destiny
  scan from an isolated folder without Python on PATH.

The first static scan identified 62 missing texts. Subsequent runtime scans
included base-game text and dynamically assembled descriptions. Provider HTTP
429 responses recovered through the existing retry logic; unchanged responses
remained pending and were translated in smaller batches. One partly Chinese
result was manually corrected. The final saved project installed 85 validated
translations with zero remaining untranslated texts in that snapshot. Previously
translated sources absent from a newer snapshot remain archived in the project.

The last running process used an earlier build of the detector and reported six
unresolved fields: four refer to intentionally empty mod localisation rows and
two to missing base-game localisation keys for row 146. The final installed
loader corrects the empty-row classification. A game restart is required to
load that final DLL and the installed dictionary. Missing source keys remain
review items; descriptions have not been invented for them. Every tooltip has
not been visually checked after installation. Runtime reports reflect their
recorded game process and timestamp; downloaded tables may include inactive mods.

Original mod data and saves were not edited. Installation uses the existing
dictionary backups and preserves other installed dictionaries. The updated app
is `GuiguModTranslator.exe`; the friends package is
`release/GuiguModTranslator-Friends.zip`.
