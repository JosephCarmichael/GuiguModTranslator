# Parallel DeepSeek translation

This records the initial parallel release. Its three-attempt retry policy is
superseded by [adaptive provider recovery](PROVIDER_RECOVERY_VALIDATION.md).

The main window and detailed editor now offer 1, 4, 8, 16, 32, 64 and 128 parallel
requests, defaulting to 16. The setting is saved with the game-folder preference.
The CLI accepts the same choices with `translate --concurrency N`.

Each request still translates at most 12 entries, with a 6,000-character batch
target (a longer individual entry stays intact). The coordinator keeps at most
the selected number of batches pending and refills slots as work completes.
Responses retain their batch identities. Only the coordinator edits or writes
the project; simultaneous completions share a checkpoint.

Cancellation stops new dispatch and waits for existing requests to finish or
hit their network timeout. Valid replies already in flight are saved, including
when another request fails. A failed job stops dispatching further batches and
surfaces the original error after draining replies. Previously translated text
is skipped when the project resumes.

HTTP 429/503 responses set a cooldown shared by the job's workers. Retry-After
seconds and HTTP dates are supported; otherwise retries use exponential backoff
and jitter, up to three attempts per batch. Cooldowns can be cancelled. The
selected number is a concurrency ceiling, not a promise of provider throughput.

## Validation on 13 September 2026

- All 34 Windows Python tests passed.
- Instrumented HTTP transports reached exactly 1, 16, 32, 64 and 128 requests
  concurrently in two waves without exceeding the chosen ceiling. Saved source
  and target mappings were checked, and only the coordinator thread wrote files.
- A fast second batch was saved while the first batch was still blocked.
- Cancellation stopped a 40-batch job after its first 16 requests and kept their
  successful replies; resuming skipped all of those saved entries.
- An exhausted-allowance error stopped further dispatch while preserving 15 other
  successful responses from the initial 16-request wave.
- Retry-After parsing, shared cooldown cancellation, HTTP 429 retries, invalid
  concurrency values, and preference preservation passed.
- Windows GUI checks verified the selector, persistence callback, forwarding
  the selected limit to the workflow, and locking the main selector during work.
- A live shared-profile OpenRouter/DeepSeek test reached **16 concurrent HTTP
  requests**, translated all **192 short entries**, and took **2.297 seconds**
  across 16 HTTP attempts with zero failed entries. This is a short-string smoke
  test, not a full-mod performance benchmark. Live 32/64/128 throughput was not
  measured; those settings were verified with offline transport tests.

The packaging self-test additionally exercises 16 simultaneous requests and
192 correctly saved translations inside the copied executable using an offline
transport, alongside its existing dependency and live translation checks.

## Evidence

- [Python tests](evidence/tests-parallel-windows.txt)
- [Live concurrency check](evidence/parallel-live-check.json)
- [GUI checks](evidence/parallel-gui-check.json)
- [Parallel-request selector](evidence/parallel-selector.png)
- [Copied single-file executable check](evidence/parallel-frozen-onefile-check.json)
- [Live translation from the rebuilt executable](evidence/parallel-frozen-openrouter-live-check.json)

Implementation references: Python's [thread-pool futures documentation](https://docs.python.org/3/library/concurrent.futures.html)
and OpenRouter's [error-handling documentation](https://openrouter.ai/docs/api/reference/errors-and-debugging).
