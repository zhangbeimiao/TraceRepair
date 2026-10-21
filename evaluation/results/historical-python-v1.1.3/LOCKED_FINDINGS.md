# Locked findings: historical-python-v1.1.3

The locked split was opened only after Agent 0.6.0-dev4 had been frozen as the evaluated runtime for
release Agent 0.6.0. The one-shot workflow had no prior runs, and each of the two locked tasks was
attempted exactly once.

HTTPie passed both target and regression tests and stopped at `awaiting_review`. youtube-dl produced a
policy-valid candidate Diff, but the target test failed; the controller stopped before regression and
returned `needs_human`. The failed patch was never accepted.

- locked workflow run: `39584933038`
- locked result: 1/2 pass@1
- complete five-task result: 3/5 pass@1
- human handoff: 2/5
- incorrect accepted patches: 0
- average completion tokens: 273.80
- P50 / P95 wall time: 11.267s / 12.600s
- terminal ledger hash: `a22b116185f95f74dd8980460764d2fb4433714233823b1b9e1fe38c073b1b3a`
- report SHA-256: `fa274cb6a02a0623be780b94ad1286ec3704a29e8e3021a8485350f29af31646`
- post-hoc locked retry: none

This small benchmark demonstrates a reproducible bounded workflow and safe rejection behavior. It does
not establish broad code-repair accuracy, and the v0.5.0 and v0.6.0 percentages are not directly
comparable because they use different task sets.
