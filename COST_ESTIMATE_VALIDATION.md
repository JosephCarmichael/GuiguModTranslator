# Full-mod estimates and friends edition eligibility

The mod list now shows estimated pence and translation availability. The friends
edition allows full translation only when a complete estimate is **at most 0.5p**
(GBP 0.005). The comparison uses the unrounded amount. Display rounds upward to
0.001p so an amount above the threshold cannot look exactly equal to it.

The estimate covers all unique nontechnical source entries, including review
candidates and saved translations. Resuming a large mod cannot reduce its full-mod
estimate below the limit. Batch size and the existing 6,000-character target set
request overhead. Chinese characters are estimated at one input and 1.5 output
tokens; other masked text at one token per three characters. JSON framing adds
four tokens per entry and system/message overhead adds 250 tokens per request.
A 30% allowance covers estimation uncertainty. This is a per-mod eligibility
rule, not an account-wide spending cap or a guarantee of the final bill.

## Pricing basis

Verified on 13 September 2026 using the
[OpenRouter model feed](https://openrouter.ai/api/v1/models) for
`deepseek/deepseek-v4.1-flash`. Its peak overrides are **USD 0.30/M input and
USD 1.20/M output**; weekend/off-peak rates are lower. The estimate uses the peak
uncached rates to avoid eligibility changing during a run. The
[model page](https://openrouter.ai/deepseek/deepseek-v4.1-flash) also lists hosts
with different prices; routed-provider cost and future price changes can affect
actual billing.

GBP conversion uses the latest working-day
[ECB reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
available at verification: 11 September 2026, EUR/USD 1.1592 and EUR/GBP 0.85815.
USD cost is multiplied by 0.85815 / 1.1592, then 100 for pence. These are dated
snapshots shipped in the application; they are not silently fetched or presented
as a live rate. The UI's estimate information explains their dates and limitations.

## Availability and persistence

Background scans update each row without sending text to a provider or writing
over saved projects. Partial/unreadable scans remain unavailable for full
translation in Friends. Destiny estimates use an isolated temporary project.

The dedicated **Translate destiny menu** action uses the existing destiny scanner
and is exempt even when its estimate exceeds 0.5p. The exemption requires the
destiny project ID and matching destiny-field source texts; merely renaming an
ordinary project does not grant the exemption. Saved installation is unrestricted.

The shared `translate` function enforces policy before requests, covering the GUI,
editor and CLI. Friends/Personal metadata is embedded into distinct builds. It
cannot be changed using normal app settings. This is application-level policy,
not protection against modifying the executable or using a recovered shared key
outside the app. Personal builds retain unrestricted translation and existing data.

## Validation

- 71 Windows unit tests passed, including exact threshold handling, saved-progress
  invariance, duplicate/technical exclusion, batch overhead, unknown coverage,
  requests blocked before sending, destiny exemption and edition metadata.
- Windows GUI checks cover estimates beside each mod, disabled expensive full
  translation, affordable mods, an expensive destiny project, and the dedicated
  destiny action while an expensive mod is selected. No paid requests or real
  installation writes were made by these checks.
- A read-only scan generated estimates for all 12 locally discovered mods.
- Friends and Personal portable builds run isolated offline self-tests, including
  policy enforcement or exemption and the expensive destiny path. Both include
  the existing destiny runtime and pass real-mod extraction checks.
- The friends CLI rejects an expensive saved project before modifying its
  checkpoint. Running translators and the game were not stopped for this update.

Evidence is saved under `evidence/cost-*` and `evidence/tests-costs-windows.txt`.
