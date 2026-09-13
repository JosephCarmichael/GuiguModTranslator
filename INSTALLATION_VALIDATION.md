# Translation installation validation

Validated on Windows 11 with the installed Tale of Immortal Unity 2020.3 build
and MelonLoader 0.5.4, 13 September 2026.

## Automated and portable checks

- 24 Python tests passed, including installation, per-mod removal, conflict
  rejection, invalid-format exclusion, lock contention, backup preservation,
  rollback after a failed write, cancellation, and the existing extractor/client tests.
- 14 C# catalog assertions passed: exact strings, markup, multiline text,
  numbered placeholders, repeated placeholders, unknown text, ambiguous matches,
  and repeated cached lookups.
- Both desktop windows passed their Windows GUI smoke tests.
- The single-file executable passed isolated-folder checks without Python on
  PATH. It includes the runtime DLL and verifies its embedded integrity manifest.
- The executable extracted a real downloaded mod and completed a live DeepSeek
  translation with formatting preserved.

## Native game check

A separately staged game instance loaded the production runtime DLL with **909
saved English translations from Workshop mod 2859071194** and one synthetic
numbered-placeholder fixture. The original running game was left running.
The production runtime registered 12 hooks without errors and loaded 910 entries.

A separate test-only Melon mod created real Unity UI Text and TextMeshPro components
inside the native game. Three real mod strings and one formatted fixture were
passed through UGUI's text setter, TMP's text setter, and TMP SetText(string, bool).
All **12 comparisons passed**. The fixture `恢复25灵力` rendered as
`Restore 25 spirit`. The test-only mod is excluded from the app and ZIP.

This verifies the actual installed text hooks inside Unity. It is not a claim
that every dialogue or gameplay screen in this mod was visited or translated.
The other TMP overloads and TextMesh hook registered successfully but were not
individually exercised in this native probe.

The installed dictionary hash in runtime status matched the deployed dictionary.
All 41 source files with hashes in the saved mod extraction still matched their
recorded hashes after installation and runtime testing.

## Removal and packaged installation

The final Windows executable removed the real mod's installed dictionary. After
restarting the test game, all three real strings remained Chinese across all
three tested UI paths, while the separately installed formatted fixture still
translated. All 12 removal comparisons passed and runtime status reported one
remaining entry, with no hook errors. The final executable then reinstalled all
909 validated real-mod translations successfully.

## Evidence

- [In-game screenshot](evidence/runtime-installed.png)
- [Native component comparisons](evidence/runtime-installed.json)
- [Loaded hooks, dictionary hash, entry count and errors](evidence/runtime-status.json)
- [Native removal comparisons](evidence/runtime-removed.json)
- [Runtime after removal and restart](evidence/runtime-removed-status.json)
- [Real installation from the final executable](evidence/frozen-install-real.json)
- [Original mod file integrity](evidence/source-integrity.json)
- [Python test output](evidence/tests-installation-windows.txt)
- [Single-file dependency check](evidence/frozen-onefile-check.json)
- [Real-mod extraction from the executable](evidence/frozen-real-mod-check.json)
- [Live translation from the executable](evidence/frozen-openrouter-live-check.json)
- [Desktop workflow smoke check](evidence/simple-gui-check.json)

## Practical limits

Restart the game after installation, updates or removal. Identical text is matched
across the game's display components, so the same source may also translate in
other mods or the base game. Conflicting installed translations are rejected.
Advanced formatting, custom renderers, image text, and unmatched generated strings
may remain Chinese. The loader targets bundled MelonLoader 0.5.x; installations
with other runtime families are rejected by preflight. No clean Windows VM or
full gameplay translation audit was performed.
