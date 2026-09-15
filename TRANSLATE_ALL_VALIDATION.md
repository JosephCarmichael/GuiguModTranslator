# Translate all — Friends 1.3.5

The main window adds **Translate all**, a 5p–£2 slider in 5p steps, an inclusive
per-mod price label, matching count and combined estimate. The selection covers
all discovered individual mods rather than only visible search results. Eligible
mods run cheapest first. The slider is remembered in the existing preferences.
The aggregate character-creation destiny project is handled by its own button.

The slider is not a total spending budget. At £2, a 5p mod, £1.80 mod and £2 mod
all match, with a combined estimate of £3.85. A £2.01 mod does not match. The
shared-key 0.5p policy remains enforced; personal-key users can use the full
slider range. Estimates remain estimates of full-mod translation, including
already saved text, so a resumed job may cost less than shown.

Unknown and incomplete estimates are excluded; the button waits for outstanding
individual-mod scans. `run_job` rechecks the freshly extracted project against
the selected price before making translation requests. If the estimate is now
too high or incomplete, that mod is skipped. The existing credential-based
policy still runs before requests. Mod jobs are sequential while each mod uses
the selected request concurrency and batch size.

Cancellation stops further mods and preserves in-flight request results using
the existing translator. A job exception stops the queue rather than repeating
authentication/funding failures for every remaining mod. Partial, empty, skipped,
failed and not-started outcomes are counted separately. A report is written to
`projects/translate-all-last.json` after each mod and at completion.

Saved projects use the same IDs and data folder as single-mod translation.
Replacing the EXE does not move or delete `%LOCALAPPDATA%\GuiguModTranslator`.
Existing wording is preserved by the normal rescan workflow and translated
entries are omitted from requests. Installed dictionaries remain in the game.

## Evidence

- `evidence/translate-all-tests-windows.txt`: **133 Windows tests passed**.
  Ten new tests cover exact boundaries, per-mod versus combined estimates,
  cheapest-first ordering, incomplete prices, shared-key restrictions,
  cancellation, failure stopping, truthful partial results, fresh-price checks,
  preserving saved wording, repeat runs without requests and stable data paths
  when a frozen app is moved to a new release directory.
- `evidence/translate-all-gui.json` and `translate-all-ui.png`: actual Windows Tk
  slider changes, waiting for estimates, search-independent selection, combined
  estimate, queue progress, cancellation, restored controls, persisted slider,
  shared-key restrictions and minimum-window layout.
- `projects/translate-all-onedir-check.json` and
  `projects/translate-all-onefile-check.json`: standalone builds run without
  Python on PATH. They exercise real extraction and saved-project reuse through
  the bulk queue with mocked translation requests and installation. The second
  bulk run makes no requests. Existing key-storage and launch-repair checks remain.
- `evidence/translate-all-package.json`: final ZIP integrity, tested EXE identity,
  Friends policy and unchanged in-game runtime. The release also checks real
  Workshop extraction.

No paid translation calls or live-game changes were made during these checks.
Actual cost depends on provider billing, and new/changed mod text can still need
translation. Previously saved translation files must be retained.
