# Automatic friends setup — app 1.3.0

Validated on Windows, 13 September 2026. The in-game translator remains the
exact 1.2.3 DLL already confirmed working by the owner.

## Shipped behavior

- Finds the installed Steam game across Steam libraries. A missing game gets a
  Steam installation button and automatic detection when the download finishes.
- Verifies bundled release hashes, installs missing compatible loader files,
  first-launch dependency archives/tools and the translation plugin.
- Preserves existing compatible loader files, other mods and dictionaries.
  Replacement plugin/tool files are backed up. Failed or cancelled writes roll
  back. An OS lock prevents simultaneous setup and releases automatically after
  a crash. Unfinished first launches keep a retry marker.
- Waits for the owner to save and close an open game before changing files.
  Launches through Steam and follows first-launch phases in a determinate bar.
  A fresh runtime status must match the running game PID and plugin version,
  contain registered hooks, report no errors and pass installation preflight.
- Installs missing Visual C++ / .NET Framework runtimes from Microsoft after
  Authenticode validation. Requests Windows elevation only when necessary.
- Includes Cancel setup, Retry setup and Launch game controls. No translation
  requests or charges are made during game setup. Friends cost limits remain.

## Evidence

- **94 Python tests passed** (88 setup/translation checks plus 6 prerequisite checks), including 16 new setup tests for clean deployment,
  integrity rejection, unsafe archive paths, preservation of other mods, rollback,
  cancellation, a game opening during installation, stale PID/status rejection,
  runtime error rejection, retry markers and released locks.
- Six prerequisite checks cover signature rejection, cancellation, quiet installation,
  failed installers, restart reporting and already-installed runtimes. The actual
  Windows Authenticode check also accepted a Microsoft-signed system runtime.
- `evidence/cold-setup-check.json`: a temporary installation started with only
  native game input files, without existing generated assemblies. The actual
  bundled Cpp2IL and Unhollower ran offline and generated **100 files in 41 s**.
  Runtime preflight passed. Repeating setup planned no changes. Detailed tool
  output is in `evidence/cold-setup-tool-1.log` and `cold-setup-tool-2.log`.
- `evidence/setup-gui-check.json` and `setup-progress-ui.png`: real Windows Tk
  startup, loading bar, cancellation control, failure state, one-click retry and
  return to the normal mod screen. Existing destiny-scan GUI checks also passed.
- `projects/autosetup-friends-onedir-check.json` and
  `autosetup-friends-onefile-check.json`: copied builds run from isolated folders
  without Python on PATH. Embedded setup hashes and actual clean deployment are
  checked, alongside translation, request recovery and edition restrictions.
- `projects/frozen-real-mod-check.json`: the EXE still reads a real Workshop mod.
- `evidence/friends-autosetup-package.json`: final ZIP integrity, every embedded
  setup asset, upstream source and the exact live-confirmed destiny DLL.

## Practical limits

A separate clean Windows PC was not available. The cold test exercised real
interface generation without launching another game into the owner's active
save environment. First game launch, Steam login behavior and Windows elevation
still need a clean-PC end-to-end check; mocked checks cover setup coordination.
This machine already has Microsoft runtimes, so installation/reboot paths were
not exercised against Windows itself. Setup does not promise compatibility with
an unrelated custom launcher, newer MelonLoader ABI or future game updates.

## Upstream inputs

- [MelonLoader 0.5.4](https://github.com/LavaGang/MelonLoader/releases/tag/v0.5.4),
  archive verified against the release's published SHA-512.
- [Cpp2IL 2022.1.0-pre-release.3](https://github.com/SamboyCoding/Cpp2IL/releases/tag/2022.1.0-pre-release.3).
- [Il2CppAssemblyUnhollower 0.4.18.0](https://github.com/knah/Il2CppAssemblyUnhollower/releases/tag/v0.4.18.0),
  with corresponding upstream source included in THIRD PARTY SOURCES.zip.
- [Unity 2020.3.9 reference libraries](https://github.com/LavaGang/Unity-Runtime-Libraries).
- [Microsoft runtime downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
  and [.NET Framework 4.8](https://dotnet.microsoft.com/en-us/download/dotnet-framework/net48).

Exact bundled hashes and URLs are in `bootstrap/manifest.json`. Game binaries,
original saves, generated game assemblies and personal projects are excluded
from the friends package.
