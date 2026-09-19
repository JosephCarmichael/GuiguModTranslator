# GitHub releases and shared translations

Repository: https://github.com/JosephCarmichael/GuiguModTranslator (private).

Version 1.4.0 implements `NEED TO ADD UPDATED.md` for the Personal and Friends
editions. Existing 1.3.x copies need this update once; those older executables
do not contain an update checker.

## Using updates

The app checks GitHub at startup and offers **Install update** when a newer
stable release exists for its edition. **Options → Check for updates** retries
the check. Installation is optional. The app downloads its edition, validates
both the ZIP and executable SHA-256 hashes, waits for translation to finish,
and restarts. The previous executable is retained as
`GuiguModTranslator.previous.exe`. Failed replacement or restart attempts roll
back to it. The app data directory, projects, titles and API-key settings are
preserved. A source checkout uses Git rather than replacing itself with an EXE.

For this private repository, invite each friend's GitHub account through the
repository's **Settings → Collaborators**. Each friend creates a fine-grained
personal access token limited to this repository with **Contents: Read-only**,
then saves it in **Options → GitHub access**. Depending on GitHub's token rules
for outside collaborators, a classic token with `repo` access may be needed;
use a dedicated account with access only to the intended repositories in that
case. See [GitHub token limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
Tokens remain encrypted for that Windows account and are never included
in the Friends download. Expired/revoked access can be replaced in the same
dialog. This login is separate from the translation API key.

## Publishing an update

The workflow in `.github/workflows/release.yml` runs after a push to `main`.
It tests and builds both Windows editions, verifies each copied executable,
and creates a release with two ZIPs and `update-manifest.json`.

1. Make and test the changes; increase `APP_VERSION` in `app_config.py`.
2. Optionally export new/corrected shared text with
   `.venv\Scripts\python.exe -X utf8 shared_library.py` and review the changes.
3. Commit and push to `main`. Wait for **Build and release** to succeed.
4. Friends are offered the new version the next time they start the app, or
   when they choose **Check for updates**.

A push does not become an available update until its tests and packaging pass.
An existing version is not overwritten; increase the version for each update.
The workflow uses the repository secret `TRANSLATION_SERVICE_JSON` for the
authorized bundled shared profile. Source control never contains that profile
or either user's personal API/GitHub credentials.

The runtime DLL in `loader/prebuilt` is our own compiled loader, with hashes
for both the binary and its C# sources. GitHub-hosted builders do not need the
game or its assemblies. If the loader changes, build and test it locally with
`loader/Build.ps1 -Test`, then run `runtime_bundle.py` and commit the updated
own-code DLL and manifest. Hosted builds fail if its source hash is stale.

Local builds still support `build_release.py --offline --edition friends` and
`--edition personal`. The `--use-prebuilt-runtime` option uses the verified
runtime without rebuilding against a local game. `publish_release.py --publish`
publishes both ZIPs using the current GitHub CLI account.

## Two GitHub accounts on this PC

The existing `AndrewEubanks` login is preserved. This workspace's GitHub CLI
login is stored separately at `/home/workbench/.config/gh-josephcarmichael`.
In the workspace's Bash terminal, use:

```bash
GH_CONFIG_DIR=/home/workbench/.config/gh-josephcarmichael gh auth status
GH_CONFIG_DIR=/home/workbench/.config/gh-josephcarmichael gh repo view JosephCarmichael/GuiguModTranslator
```

This repository's Git credential helper is configured locally to use that
account; other repositories keep their own configuration. The previous remote
is retained as `previous-origin`.

## Shared translations

`shared-library/index.json` maps stable mod identities to English titles and
small compressed files of exact source/translation pairs. The Friends and
Personal packages include a snapshot. The app refreshes the index from GitHub
and downloads the selected mod's file before translating. A SHA-256 check
guards every downloaded file. Matching local/shared text is reused without
translation requests; changed source text remains pending. Local translations
and edits take priority. **Translate mod again** deliberately bypasses shared
reuse for that job. No account is needed to reuse the bundled snapshot.

The app does not silently upload friends' projects. The publisher reviews and
exports saved translations with `shared_library.py`, then commits the shared
files. Exports contain only stable identities, source text, valid English
translations and titles: no local paths, credentials, game binaries, saves or
provenance metadata. Incomplete projects can contribute valid entries without
being labelled complete.

The initial export has 1,349 translations across 4 mods and 14 titles, with
108,899 bytes of compressed translation files. At that sample's compression
ratio, one million similar entries would be about 81 MB, excluding Git history
and indexes. Long dialogue can use substantially more space. The files are
split per mod to keep individual files small. Git history grows as versions
are committed; periodically assess repository size rather than assuming an
unlimited database. See GitHub's
[repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)
and [release storage guidance](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Translation and interface changes

- English mod titles are automatic, validated, saved, reused and searchable
  alongside their original names. **Title again** retries a selected title;
  failed requests keep the previous wording.
- **Translate mod again** uses the selected key, request concurrency and batch
  size. It saves the previous project under `retranslation-backups` before new
  requests. Failures retain the old text and mark it pending review. Resume
  retries unfinished entries. CLI users can pass `translate --retranslate`.
- Completion ticks require usable English for every nontechnical entry,
  preserved formatting, no pending review and no unreadable/partial files.
  Destiny projects also require their runtime inventory and no unresolved gaps.
- Thumbnails decode the game's `ModProjectPreview.png` from Workshop,
  local project and debug-export layouts. Missing or invalid previews fall back
  to a text label. Original mod files are never modified.
- Both editions use the same library, thumbnails, editor, bulk tools, destiny
  tools, update mechanism and key controls. The Friends shared-key cap still
  guards paid requests; Personal has no cap. Personal-key selection is unchanged.
