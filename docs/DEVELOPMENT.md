# Development and releases

[User guide](USER_GUIDE.md) · [Project overview](../README.md)

## Run and test

Use Windows Python 3.13:

```bat
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -X utf8 entry.py
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Runtime-loader development also needs the .NET SDK, the .NET Framework 4.7.2
targeting pack, and a compatible local game installation. Build and test with
`loader/Build.ps1 -Test`, then run `runtime_bundle.py` to update the prebuilt
loader and its source/binary hashes. Game assemblies are not redistributed.

Generated evidence and local validation reports are ignored. Keep reproducible
tests in `tests/`; diagnostic scripts can write into `evidence/`.

## Build a private release

Install PyInstaller and provide an authorized shared profile in the ignored
`bundled_service.json`. The existing build embeds that key in the executable.

```bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -X utf8 build_release.py --offline --use-prebuilt-runtime --edition friends
.venv\Scripts\python.exe -X utf8 build_release.py --offline --use-prebuilt-runtime --edition personal
```

Use `--side-by-side` to keep existing app files. Offline builds skip live
translation checks; they still test the packaged app. Preserve dependency notices
and source archives in distribution packages.

Increment `APP_VERSION` before publishing a new release. GitHub Actions tests and
builds both editions, then publishes their ZIPs and `update-manifest.json`.
It uses the `TRANSLATION_SERVICE_JSON` repository secret. A code push becomes an
offered update only after successful packaging and publication. Existing release
versions are not overwritten.

For local publishing, authenticate GitHub CLI with repository access and run
`publish_release.py --publish` after building both editions.

## Prepare public distribution

The existing v1.4.0 Friends and Personal executables contain the configured
shared translation key. A public build needs to omit that credential and let
users configure their own translation access, or use a separately designed
hosted service.

Before changing repository visibility:

- Build and test the intended public package, including free translation if it
  is advertised. The v1.4.0 EXE does not contain the newer free mode.
- Resolve embedded credentials in existing downloadable releases.
- Review retained Git history: removing local reports from the current tree
  does not remove older committed reports or screenshots.
- Verify downloads, update checks, and library reads without a GitHub login.

The stable download page is
[Releases](https://github.com/JosephCarmichael/GuiguModTranslator/releases/latest).
It remains restricted while the repository is private.

## Publish shared translations

```bat
.venv\Scripts\python.exe -X utf8 shared_library.py
```

Review and commit the resulting `shared-library/` files. The index maps stable
mod identities to titles and compressed source/translation pairs. Exports omit
local paths, credentials, saves, and provenance metadata. Only valid entries are
included; partial projects can contribute usable translations.

Clients download the index and needed mod files, verify hashes, and reuse exact
matches while preserving local edits. This does not upload client projects.
Keep files split by mod and monitor repository size as Git history grows.

## Useful CLI commands

```bat
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" install projects\MOD_ID
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" installed
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" uninstall MOD_ID
.venv\Scripts\python.exe -X utf8 entry.py translate projects\MOD_ID --concurrency 16 --batch-size 48
.venv\Scripts\python.exe -X utf8 entry.py scan-destinies --install-detector
```

The CLI `translate` command saves a project; run `install` afterward.
`--retranslate` requests fresh translations with a backup of the previous project.
