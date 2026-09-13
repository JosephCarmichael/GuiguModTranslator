# Direct-provider throttling and automatic recovery

## Diagnosis

The user's portable app selected the personal **direct DeepSeek** profile rather
than the shared OpenRouter profile used by the previous live concurrency check.
The original failing job did not record HTTP diagnostics, so its historical
status code could not be recovered. A subsequent bounded reproduction using the
same direct profile and a copy of 192 real untranslated entries from mod
2814696167 returned **12 HTTP 429 responses** before recovering.

This establishes provider-side rate limiting during reproduction, not the precise
account quota or whether other concurrent account activity contributed. A single
12-entry diagnostic request had succeeded. Changing API provider is not required
for the demonstrated recovery.

The previous client stopped the entire translation after any one batch exhausted
three short retries. It also grouped timeouts, rate limits and several server
errors under the same generic “busy” message.

## Change

- The selected parallel-request value is now a ceiling. A shared admission gate
  limits actual HTTP requests and halves concurrency after transient failures.
  One burst of errors counts as one reduction, rather than immediately reducing
  once per failed request in that wave.
- All workers share the cooldown. Retries are staggered after recovery starts,
  and capacity increases gradually after sustained success, up to the ceiling.
- Up to eight attempts per batch replace the old three-attempt budget. Retry-After
  is honored; otherwise the delays are 5, 10, 20, 40 and then 60 seconds plus jitter.
- Progress shows actual concurrency, the HTTP status and a retry countdown.
  Cancellation still stops waiting workers and preserves successful in-flight replies.
- Temporary errors embedded in HTTP 200 JSON responses use the same recovery path.
  Authentication, credit and access errors stop immediately with a precise status.
- `request-errors.jsonl` records provider, model, status, attempt, delay and active
  request limit. It excludes API keys, submitted text and raw response payloads.
- Persistent outages remain bounded by the retry budget and produce a specific
  error rather than the old generic busy message. The app cannot remove an
  account or provider quota.

## Validation on 13 September 2026

All **43 Windows Python tests passed**, including recovery after four consecutive
503 responses, HTTP-200 rate-limit errors, actual admission at the reduced limit,
error-wave grouping, gradual capacity recovery, cancellation during cooldown,
diagnostic logging, eight-attempt exhaustion, and the previous concurrency,
translation and installer tests. Both GUI smoke checks passed.

The real-text check used **192 entries / 5,303 source characters** through direct
DeepSeek with a ceiling of 16. It received 12 HTTP 429 errors, automatically reduced
concurrency through **8 and 4**, and completed all 16 batches after 28 HTTP attempts
in **25.237 seconds**. It saved **165 validated translations**. The other **27 entries**
were unchanged or blank responses and remain untranslated for review; no claim
is made that those were successfully translated. The check used a separate output
folder and did not overwrite the user's active project.

The copied executable self-test also forces four consecutive HTTP 429 responses
and verifies that a fifth attempt succeeds and produces a diagnostic log.

## Evidence

- [Direct-provider result](evidence/direct-provider-recovery.json)
- [Actual HTTP 429 retry events and concurrency reductions](evidence/direct-provider-retry-events.jsonl)
- [43-test output](evidence/tests-recovery-windows.txt)
- [Recovery in the copied executable](evidence/recovery-frozen-onefile-check.json)
- [Rebuilt executable live check](evidence/recovery-frozen-live-check.json)

References: [DeepSeek rate-limit documentation](https://api-docs.deepseek.com/quick_start/rate_limit/)
and [OpenRouter error handling](https://openrouter.ai/docs/api/reference/errors-and-debugging).
