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

Source launches preserve local provider settings. Choose Google in **Translation
models** for keyless translation. Local credentials and generated evidence are
ignored by Git. Keep reproducible tests in `tests/`.

Runtime-loader development also needs the .NET SDK, the .NET Framework 4.7.2
targeting pack, and a compatible local game. Run `loader/Build.ps1 -Test`, then
`runtime_bundle.py` to update the prebuilt loader and its source/binary hashes.
Game assemblies are not redistributed.

## Build a credential-free release

```bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -X utf8 build_release.py --offline --use-prebuilt-runtime --edition public
```

No translation secret or service profile is required or included. Packaging scans
the executable and embedded Python modules for credential files and key patterns.
The publisher repeats this check before uploading. Portable self-tests verify a
clean start without keys, encrypted user-key storage/removal, translation,
installation, and update behavior using isolated fixtures.

The output is `release/GuiguModTranslator-Public.zip`. Use `--side-by-side`
to build a separate timestamped copy. Preserve dependency notices and source
archives when distributing. `--offline` skips live Google checks. Run the copied
EXE with `--self-test-live PATH_TO_REPORT.json` for a small live Google test.

Increment `APP_VERSION`, test, commit, and push to `main`. GitHub Actions builds,
verifies, and publishes the Public ZIP and `update-manifest.json`, using only
the workflow's GitHub publishing token. That token is never passed to packaging.
No translation credentials are stored in Actions secrets.

The manifest maps Public, Friends, and Personal clients to the same key-free
package, preserving updates for older installations. Existing release versions
are not overwritten. To publish locally after building, authenticate GitHub CLI
with repository access and run `publish_release.py --publish`.

## Public repository visibility

The package is designed for public distribution; the GitHub repository remains
private until its visibility is changed. Review retained Git history before
changing visibility: removing reports from the current tree does not erase their
older committed copies. Verify anonymous downloads and shared-library access
after changing visibility.

The stable download page is
[Releases](https://github.com/JosephCarmichael/GuiguModTranslator/releases/latest).

## Publish shared translations

```bat
.venv\Scripts\python.exe -X utf8 shared_library.py
```

Review and commit the resulting `shared-library/` files. Exports contain stable
mod identities, titles, and valid source/translation pairs. They omit local paths,
credentials, saves, and provenance metadata. Partial projects can contribute
usable entries.

Clients verify hashes and reuse exact matches while preserving local edits.
They do not upload projects. Keep files split by mod and monitor repository size.

## Useful CLI commands

```bat
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" install projects\MOD_ID
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" installed
.venv\Scripts\python.exe -X utf8 entry.py --game "C:\path\to\game" uninstall MOD_ID
.venv\Scripts\python.exe -X utf8 entry.py translate projects\MOD_ID --concurrency 16 --batch-size 48
.venv\Scripts\python.exe -X utf8 entry.py scan-destinies --install-detector
```

The CLI `translate` command saves a project; run `install` afterward.
`--retranslate` backs up the project before requesting fresh translations.
Google serializes requests regardless of the AI concurrency setting.
