# Personal OpenRouter keys — Friends 1.3.3

Friends can click **API key…** on the main window or **Options → API key…**,
paste their own OpenRouter key and choose **Save personal key**. The main window
identifies personal billing and immediately enables full-mod translation above
the shared-key cap. Estimates remain visible. **Use shared key** removes the
saved encrypted personal key and reinstates the existing **0.5p (£0.005)** cap.
The app cap does not apply when the user's own OpenRouter key is used. OpenRouter
account credit, account/key limits and service availability still apply.

The same captured profile is passed to the policy check and all requests for a
translation job. A settings change in another app instance cannot authorize a
large job with a personal key and then bill the bundled key. Personal credential
errors stop the job; they never switch to shared credit. Copying the bundled key
into a local service file or the personal-key dialog does not lift its cap.
This policy also applies to the editor and CLI through the shared translator.

The key field is masked and never prefilled with an existing credential. Saving
checks the format without making a request or checking account credit. The key
is protected using Windows user-scoped DPAPI and stored as encrypted data in
`%LOCALAPPDATA%\GuiguModTranslator\openrouter-access.json`. The file is excluded
from diagnostics and release bundles. A damaged or unreadable file produces an
explicit settings error without credential fallback. An explicit shared-key
selection also overrides legacy `service.json`; that legacy file is preserved.

## Validation

- `evidence/personal-key-tests-windows.txt`: **123 Windows tests passed**, including
  ten new credential/policy tests exercising actual DPAPI, save/reload, invalid
  input, preservation on save failure, cap removal/restoration, no shared-key
  relabelling, corrupt settings, request failure and the credential snapshot.
- `evidence/personal-key-gui.json` and `personal-key-ui.png`: real Windows Tk
  settings dialog, masked entry, invalid-key feedback, immediate cost gating,
  cancel, removal, unavailable key changes during a translation, and minimum
  window layout. No game changes or paid requests.
- `projects/personal-key-onedir-check.json` and
  `projects/personal-key-onefile-check.json`: copied executable checks without
  Python on PATH, including real encrypted-key storage, an over-cap translation
  using the personal profile with mocked requests, and restored shared gating.
  The existing launch repair and translator deployment checks remain included.
- `evidence/personal-key-package.json`: final ZIP identity/integrity, embedded
  access modules, app version, Friends edition policy, unchanged 1.2.3 in-game
  runtime and exclusion of personal credential files. Real Workshop extraction
  is also checked in the release build.

No valid personal key or paid OpenRouter call was needed for testing. The saved
key's server-side validity and available account credit are checked by OpenRouter
when the user requests a translation. The previous launch-repair validation and
its full-game testing limits continue to apply.

## Implementation references

- [Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
  documents Windows logon-credential protection; the machine-wide option is not used.
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) documents the
  Bearer Authorization header used by the existing request transport.
