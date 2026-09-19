# Updated requirements — 1.4.0

Source: `NEED TO ADD UPDATED.md`.

| Requirement | Implementation and verification |
| --- | --- |
| Repository under JosephCarmichael | Private `JosephCarmichael/GuiguModTranslator`; authenticated account and repository push/admin permissions verified. Existing AndrewEubanks credentials are retained separately. |
| Offer updates in the Friends download | `app_updates.py`, `github_client.py`, the desktop update banner and `.github/workflows/release.yml`. Newer stable versions select the same edition; ZIP and EXE checksums are required before replacement. Unit tests cover both editions, wrong hashes, unsafe archives, cancellation, retained data, rollback and credential-safe redirects. |
| Automatically translate every mod title | `mod_titles.py` and the background desktop worker; valid cached/shared titles are reused first. A refresh during a request queues newly discovered names. Regression tests cover that race and invalid outputs. |
| Persist titles and avoid repeated generation | `mod-titles.json` and the shared title index; exact source-name matches survive restart. Invalid/stale titles retry, and title retranslation preserves the old wording on failure. |
| Retranslate bad wording using user settings | **Translate mod again** forwards selected concurrency and batch size; `translation.py` snapshots the selected credential, backs up the old project and bypasses shared reuse. Tests prove backup, retry after failure, and retaining old text without a false completion tick. |
| Tick fully translated mods | `saved_translations.status_of` is shared by the job and saved-project list. It validates English, formatting, pending review and extraction/destiny gaps. |
| Use mod thumbnails | `thumbnails.py` locates Workshop/local/debug previews and decodes the game encoding before Pillow reads them. Native UI checks display 15 actual local previews. |
| Improve appearance and usability | `desktop_view.py`: searchable library, artwork, selected-mod details, visible completion/access status, settings, retranslation controls, update banner and main action. Both editions have screenshot evidence. |
| Personal feature parity without Friends spending limit | Both editions use the same implementation. Existing policy tests verify Personal is unrestricted and Friends paid requests keep their cap. API-key selection is unchanged. Already saved/shared text makes no paid request. |
| Share titles/translations to avoid duplicate requests | `shared_library.py`: validated per-mod compressed dictionaries, exact-source matching, SHA-256 verification, local-edit precedence, bundled fallback and publisher export. Tests verify reuse without even loading API credentials, changed-source misses, damaged-cache rejection and repeat-download avoidance. |
| Explain storage practicality | `RELEASES_AND_SHARING.md` records the measured initial export and an explicitly approximate one-million-entry projection, with GitHub limits linked. |

## Local verification

- Windows unit-suite output: `evidence/updated-tests-windows.txt`.
  All 197 tests pass locally and on the clean GitHub Windows runner.
- Native Windows UI test: `tests/updated_gui_smoke.py` and
  `evidence/updated-gui-check.json`, with Personal/Friends screenshots.
  It uses temporary app data, actual local artwork, a fixture provider and
  stubbed setup. No game files or real projects are changed and no paid request
  is made.
- Source self-test: `evidence/updated-source-selftest.json` (24 checks), including
  encoded thumbnails, shared reuse and update ZIP/EXE validation.
- Loader rebuilt locally against the installed game; 33 catalog assertions pass.
  `loader/prebuilt/manifest.json` ties the own-code DLL to its C# sources.
- Initial Personal and Friends folder/single-file builds passed their offline
  self-tests. Final published artifacts are additionally verified by the
  GitHub release workflow and a download check after publishing.

## Published release verification — 19 September 2026

- [Build and release succeeded](https://github.com/JosephCarmichael/GuiguModTranslator/actions/runs/35443569840)
  for commit `a50e837863eeb327d7fb72bbfecedb97fd561a56`.
- [v1.4.0](https://github.com/JosephCarmichael/GuiguModTranslator/releases/tag/v1.4.0)
  contains both edition ZIPs and `update-manifest.json`.
- The actual private-repository updater detected the release from version
  1.3.8, selected each edition correctly, downloaded it and verified both
  checksums. Version 1.4.0 correctly reports no newer release.
- Published Friends EXE: 25 checks pass; Personal: 24 checks pass. The extra
  Friends check verifies the shared-key cap. Results are saved in
  `evidence/published-friends-selftest.json` and
  `evidence/published-personal-selftest.json`.
- Published Personal also passes real-mod extraction. The local root Personal
  EXE and both local release ZIPs now match the published files.
- `evidence/github-release-check.json` records hashes and verifies that the
  source/portable credential files and title caches survive these checks.
  No paid translation requests were made.
- The app's private GitHub client successfully downloads the shared index and
  matching dictionaries. Export now selects only canonical project folders,
  excluding diagnostic copies. A newer bundled index wins over an older
  downloaded cache. The final library has 1,349 entries, 14 titles and 108,899
  bytes of compressed translation data.
- A native Windows child-process test also verifies the updater waits for the
  old process to exit before replacement. Replacement/rollback and data
  preservation are covered by the Windows unit tests.

## Scope of the checks

Update networking is tested with fixtures and verified against the actual private
GitHub repository. Game setup and runtime translation behaviour retain the
existing test suite; this change does not claim a new visual inspection of every
mod's in-game dialogue. The shared library includes valid entries from incomplete
projects and does not claim those whole mods are completely translated.

The repository is private. Friends must receive an invitation and configure
GitHub access to retrieve later updates; their translation API-key setup stays
the same. Existing 1.3.x installations require the 1.4.0 download once.
