# Launch repair update — 15 September 2026

The Personal installation now uses Windows' existing ASCII short folder name
(`DF1D~1`) in Steam's `installdir`. The game directory stays in place. Setup
prefers this repair where available; the earlier rename/junction strategy remains
as a fallback. A Steam manifest that names a link to the game is accepted only
when that link resolves to the exact validated game directory.

`destination()` now resolves the game root before checking output containment,
so the short name does not produce a false "outside the game" error. Internal
reparse-point rejection and traversal checks still apply.

Validation:

- 169 Windows unit tests pass, including manifest aliases, short-name repair
  while the app is inside the game, interrupted preference saving, repeat startup,
  and setup destinations reached through a root alias.
- `evidence/launch-short-path-native.json` reproduces the original silent exit
  with the exact bundled proxy, then reaches the native test program through
  the repaired manifest path without moving files.
- The real Steam installation was repaired. Its executable hash is unchanged;
  the original game and translator paths remain valid. Manifest backups are in
  `%LOCALAPPDATA%\GuiguModTranslatorRepair\2026-09-15\launch-repairs`.
- Real game setup installed the current translation plugin and confirmed a live
  process running runtime version 1.2.3 with registered hooks and no startup errors.
- All 14 Chinese mod titles were translated and saved through the configured
  API. Title validation now permits translated leading `[author]` labels while
  preserving runtime placeholder checks.

The short-name repair can be undone with Steam closed by restoring only the
recorded original `installdir` value in its current manifest. No directories need
moving for this strategy. The historical rename instructions below apply only
to repairs whose journal strategy is `rename` (or older journals without strategy).

---

# Friend's instant Steam exit — 1.3.2 repair

## Diagnosis

The supplied `release/Guigu-Logs.txt` was collected at 19:55 UTC on 13 September
2026. It confirms Windows ANSI code page 1252 and an unrepresentable game path,
`E:\SteamLibrary\steamapps\common\鬼谷八荒`. Microsoft runtimes are present.
Steam starts the process and records exit code 0 about two seconds later, including
the 20:51:38–20:51:40 local-time attempt. There is no fresh translator status.
The bundled MelonLoader log is from a developer's `D:\Project` build in 2023,
so its warnings do not describe this friend's failed launch.

The [MelonLoader 0.5.4 proxy source](https://github.com/LavaGang/MelonLoader/blob/v0.5.4/Proxy/Core.cpp)
uses `GetModuleFileNameA` followed by an ANSI directory check. With this code page,
the Chinese characters become question marks. `IsUnityGame` then fails and
`KillItDead` terminates the process with code 0 before normal logging or main.

## Repair

`launch_repair.py` runs before translator setup when the game path cannot be
represented by the Windows ANSI code page. It waits for the game and Steam to be
closed, renames the game directory on the same volume to `TaleOfImmortal` (or an
unused numbered name), and changes only `installdir` in this game's Steam manifest.
A Windows junction at the original path keeps existing mod/dictionary references
valid. The app then launches using Steam's repaired installation record.

The manifest is backed up in `%LOCALAPPDATA%\GuiguModTranslator\launch-repairs`.
A journal supports recovery after interruption. Ordinary write/junction failures
roll back the directory and manifest; unrelated manifest edits are not overwritten.
Repairs preserve executable bytes, saves, Workshop content and installed mods.
An explicit pending marker requires a fresh running translator status before
setup reports ready. The desktop adopts the repaired path on successful setup.

The portable app and its data must be outside the game directory being renamed.
If the library's parent path also cannot be represented, setup explains that the
game needs moving to an English-named Steam library instead of attempting a bad
rename. No Windows locale change or MelonLoader upgrade is required.

To manually undo a completed repair, close the game, Steam and translator;
remove only the old-path junction (do not delete its contents), rename the actual
game directory to its recorded original name, and restore the backed-up manifest.
Use the matching `repair.json` to identify the exact paths. If Steam has updated
the game since repair, change only its current manifest's `installdir` back to
the original name rather than restoring an obsolete full manifest.

## Validation and limits

- `evidence/launch-repair-native.json`: a native Windows test executable loads
  the exact proxy SHA-256 from the friend's report,
  `4ecc46869239ad191010c5206436067464cf28736742d9ebd206269279b63c81`.
  At ACP 1252, launching via the Chinese folder exits 0 before main. After the
  real repair, launching via the directory read from the updated manifest reaches
  main and forwards the version API call successfully (expected exit code 42).
  The real rename, junction, backup and manifest edit were exercised in a fixture.
- `evidence/launch-repair-tests-windows.txt`: all 113 Windows tests passed, including
  preservation, cancellation, occupied destinations, malformed manifests, BOM
  preservation, junction failure, manifest-write failure, Steam reopening,
  interrupted rename recovery, preference-write recovery and unrelated edits.
- Standalone folder and single-file builds exercise the repair from isolated
  directories without Python on PATH. Their reports are
  `projects/launch-fix-onedir-check.json` and
  `projects/launch-fix-onefile-check.json`.
- `evidence/setup-gui-check.json`: real Windows Tk setup/retry checks passed,
  including adoption of the repaired installation path.
- `evidence/launch-repair-package.json`: final
  `release/GuiguModTranslator-Friends-LaunchFix-1.3.2.zip` passed ZIP integrity,
  embedded repair-module, Friends policy and exact tested-EXE checks. The working
  translator DLL remains version 1.2.3 with its original SHA-256. The standalone
  EXE also passed extraction of a real Workshop mod. No paid API tests were run.

The native test uses `--no-mods` and proves the specific pre-main path failure is
removed. It does not launch Unity or verify the friend's PC end to end. The real
game installation and Steam session on the development PC were left unchanged.
The friend's next run must still verify full startup, Steam sign-in and the live
translator. The app retains Collect logs if another startup problem remains.
