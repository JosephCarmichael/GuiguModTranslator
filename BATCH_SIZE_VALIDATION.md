# Larger batches and provider-switch resume

The desktop and editor now offer 12, 24, 48 or 96 entries per request. The
default is 48, with the existing 6,000-source-character target retained. Entries
are kept whole. Output truncation splits a batch in half and retries its parts;
an individually oversized entry is reported while other entries continue.
Concurrency is still a separate setting and the existing provider cooldown and
adaptive concurrency handling remain in use.

Rescanning retains translations and their model metadata. Changing provider or
batch size requests only untranslated entries; progress shows the saved total.
An isolated release can be built using `--offline --side-by-side` without
overwriting or stopping an existing executable.

Testing the next untranslated entries also exposed two validation problems:
angle-bracket narration was hidden as if it were a formatting tag, and English
after a percentage could be misread as a printf placeholder. Narration now stays
visible to the model, while its brackets and known rich-text tags are protected.
Numeric percentages are recognized separately from printf placeholders.

## Validation on 13 September 2026

- All 53 Windows unit tests passed, including batch counts at all four sizes,
  the character target, recursive truncation splitting, isolated oversized
  entries, provider changes after rescanning, narration and percentages.
- Both Windows GUI smoke checks passed. The main GUI check verifies batch
  choices, preference saving, forwarding to the worker, and locking during work.
- The portable folder and single-file executables pass isolated offline checks,
  including two 48-entry requests, narration, percentages and provider recovery.
  Real-mod extraction from the portable executable also passes.
- OpenRouter accepted a real 48-entry request (1,765 source characters), saving
  47 translations in 10.465 seconds. One percentage entry was rejected by the
  validator. After the percentage fix, resuming sent only that one remaining
  entry and saved it successfully: all 48 sample entries are now translated.
  This is a functional check, not a sustained-throughput benchmark.
- The user's provider settings were backed up and switched to the configured
  OpenRouter profile, retaining concurrency 16 and selecting batch size 48.
  Their saved project was backed up and remained byte-for-byte unchanged with
  3,794 translations. Live checks wrote to separate sample project folders.
  The existing app was not stopped; the new build must be opened to use its code.

## Evidence

- [53-test output](evidence/tests-batches-windows.txt)
- [48-entry OpenRouter result](evidence/openrouter-large-batch-check.json)
- [Resume sends only the remaining entry](evidence/openrouter-batch-resume-check.json)
- [Provider switch and preserved project](evidence/openrouter-switch.json)
- [Portable folder checks](evidence/batches-frozen-onedir-check.json)
- [Portable single-file checks](evidence/batches-frozen-onefile-check.json)
- [Real-mod extraction](evidence/batches-frozen-real-mod-check.json)
- [GUI checks](evidence/batches-gui-check.json)
