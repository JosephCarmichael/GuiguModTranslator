# Portable Windows release

The friends package is `release/GuiguModTranslator-Friends.zip`.
It contains a single-file Windows executable, a small launcher, instructions
and dependency license texts. Python 3.13, Tcl/Tk and the required Python/native
packages are embedded in the executable. No separate Python installation is
needed. The app requires 64-bit Windows 10/11 and internet access to translate.

The main screen has a searchable mod list and one **Translate and install**
button. Extraction, translation and installation run together. Restart the game
to load the installed text. The Options menu includes the detailed editor,
installation of saved work, and removal of a selected mod's translations.
The final message distinguishes installed translations, partial work,
cancellation and errors. The included runtime targets the game's bundled
MelonLoader 0.5.x; no mod bundles or save files are patched.

The shared build contains the explicitly supplied limited OpenRouter key and
uses `deepseek/deepseek-v4.1-flash`. The owner's direct account settings and
existing projects are kept in local app data and are excluded from the ZIP.

Build process: `build_release.py`. It first builds and tests a folder bundle,
then builds a single-file executable, copies it to an isolated temporary folder,
removes Python locations from that process's search path, checks dependencies,
extracts a real downloaded mod and performs one small live translation.

Validation and native game evidence are saved in
[INSTALLATION_VALIDATION.md](INSTALLATION_VALIDATION.md), including screenshots,
component comparisons, source-file integrity checks, executable installation,
and removal verified after a game restart.

These are tests on this Windows machine using isolated folders and process
environments. A separate clean Windows virtual machine was not available for
validation.
