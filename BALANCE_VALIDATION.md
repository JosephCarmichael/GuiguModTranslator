# Balance display — Friends 1.3.6

Release: `release/GuiguModTranslator-Friends-1.3.6.zip`.

The top-left header shows the selected OpenRouter key's remaining allowance as
estimated GBP, with its original USD value underneath. The old shared-key 0.5p
and destiny-menu availability banner is removed. This removes the banner text;
the existing shared-key translation policy remains in place.

Confirmed provider response charges decrease the cached balance immediately,
including billed responses that require a retry. The UI updates within 500 ms.
Saved text reuse sends no request and makes no deduction. Duplicate generation
IDs are ignored. Background refresh runs every 30 seconds and after a job;
delayed usage reporting cannot restore an already recorded charge. Requests and
refreshes are coordinated so concurrent batches are not double counted.

Balances persist separately by hashed key identity, without storing credentials
in the cache. The cache is excluded from the portable package. An unavailable
endpoint preserves the last known balance; unlimited keys without a reported
allowance display that limitation instead of a fabricated amount.

The previous read-only live check (`evidence/balance-live-read.json`) reported
$0.566312218, displayed as approximately 41.92p using the app's existing 0.74
GBP/USD estimate. The requested 57p is therefore not hard-coded. This is key
allowance, not a query of total account funds. API field semantics are documented
by [OpenRouter](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).

Validation completed on Windows:

- `evidence/balance-tests-windows.txt`: all 148 unit tests passed, including
  deductions, parallel requests, duplicate responses, delayed refreshes, key
  separation, persistence and failed refreshes.
- `evidence/balance-gui.json` and `balance-header-ui.png`: actual Tk window,
  top-left layout, removed banner, displayed deduction and key switching passed.
- `projects/balance-onedir-check.json` and `balance-onefile-check.json`: existing
  standalone executable checks passed, including the actual request path with
  mocked billing, reconciliation, saved translation reuse and key handling.
- `evidence/balance-package.json`: final ZIP integrity, identity with the tested
  executable, embedded balance module and exclusion of the balance cache passed.

The resumed work reran the unit and Windows GUI checks, completed the final
package verification and created the versioned release. No paid translation
requests were made during this completion pass. Billing tests use simulated
provider responses; the previous live allowance check was read-only.
