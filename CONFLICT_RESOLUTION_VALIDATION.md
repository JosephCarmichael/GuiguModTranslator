# Automatic translation conflict resolution

Different translations for identical source text no longer stop installation or
cause the loader to drop that text. The most recently installed dictionary wins
at runtime. An increasing installation sequence avoids clock-dependent priority;
legacy dictionaries fall back to installation timestamp and then ordinal mod ID.
Reinstalling a dictionary gives it priority again.

Each mod retains its own translations in the installed store. Removing the winning
mod reveals the next eligible dictionary; dictionaries with missing source paths
are excluded. Install/update/remove still back up the previous store. The saved
translation project and original mod files are not rewritten to resolve conflicts.

Within a project, validated manual edits take priority over existing translations,
then machine output. Stable unit IDs and translation text break ties. Invalid,
technical and review-pending entries retain their existing exclusion rules.
The UI and CLI report the number of distinct conflicting source texts resolved.
Runtime 1.1.0 records its resolved count in `runtime-status.json`.

Both **Translate and install** and **Options → Install saved translations** use
the policy. The latter can retry a previously blocked installation without making
translation API requests. CSV import validation and ambiguous formatted-template
matching remain separate checks.

## Validation

- 57 Windows Python tests passed. Coverage includes conflicting install success,
  unchanged original dictionaries and project data, backups, reinstall priority,
  legacy-store migration, order-independent preference for manual edits,
  independent removal, failed-write rollback, locks and invalid-entry exclusion.
- 25 C# catalog assertions passed against the production resolver, including JSON
  serialization, clock-independent installation priority, legacy timestamps and
  ties, missing source paths, blank translations, removal and unchanged losing
  dictionaries. The production MelonLoader DLL compiles against the local game.
- The Windows GUI smoke test confirms the automatic conflict count is displayed.
- Copied folder and single-file builds pass offline self-tests, including a
  conflicting installation into a temporary game directory and independent
  removal. The production loader and integrity manifest are bundled.
- Portable real-mod extraction passes. No running translator or game was stopped,
  no live translation API was called, and this validation does not claim a new
  in-game visual probe. The new runtime takes effect after installation and restart.

Evidence: [Python tests](evidence/tests-conflicts-windows.txt),
[build and C# checks](evidence/build-conflicts-check.txt),
[GUI](evidence/conflicts-gui-check.json),
[folder build](evidence/conflicts-frozen-onedir-check.json),
[single-file build](evidence/conflicts-frozen-onefile-check.json),
[real mod](evidence/conflicts-frozen-real-mod-check.json).
