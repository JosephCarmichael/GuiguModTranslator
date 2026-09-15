# Shared-key cap — 1.3.7

Changed the shared-key full-mod estimate cap from 0.5p to **5p (£0.05)**.
Exactly 5p is allowed; anything above 5p remains blocked on the shared key.
The same policy controls single-mod translation and the Translate all queue.
UI status, rejection messages and packaged instructions now say 5p.
The balance display and personal-key behavior are retained.

Validation: 148 Windows unit tests passed (`evidence/five-pence-tests-windows.txt`).
Boundary coverage allows 3p and 5p, rejects 5.00000001p, and verifies that the
bulk queue includes mods previously excluded by the half-penny cap. The Windows
bulk GUI smoke check also passed (`evidence/five-pence-gui.txt`), including
switching back to the shared key with a 5p mod available.

Release: `release/GuiguModTranslator-Friends-1.3.7.zip`. Standalone executable
reports are `projects/five-pence-onedir-check.json` and
`projects/five-pence-onefile-check.json`; final package evidence is
`evidence/five-pence-package.json`. Checks use mocked translation responses and
make no paid API requests.

The first standalone checks encountered a Windows clipboard held by another
application. The self-test now records that specific external lock as an
unavailable clipboard check while still verifying the saved log contents and
running every remaining check. Other clipboard failures still fail validation.
No production clipboard behavior was changed.
