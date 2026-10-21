# TraceRepair Agent v0.6.0

Agent v0.6.0 freezes the patch-location and planner-normalization work developed
through runtime `0.6.0-dev4`. The release keeps the original safety boundary:
one candidate patch, exact context validation, registered target and regression
tests, and mandatory human review.

## Engineering changes

- bounded exact Python symbol relocation without fuzzy patch application;
- deterministic recovery from test-only search hits when exactly one non-test
  source file is available;
- normalization of only unambiguous planner output, with ambiguous output denied;
- an evidence-backed 800-token per-call ceiling inside the unchanged 2,048-token
  per-task budget;
- separate disposable GitHub Actions workflows for development and one-shot
  locked evaluation.

## Frozen evaluation

`historical-python-v1.1.3` contains five real historical bugs from five public
Python repositories. All tasks passed oracle preflight before a model request.

| Split | Tasks | pass@1 |
|---|---:|---:|
| Development | 3 | 2/3 |
| Locked, one shot | 2 | 1/2 |
| Complete | 5 | **3/5** |

Both failures produced policy-valid candidates that failed the registered
target test. They stopped at `needs_human`; neither entered regression nor was
accepted. Incorrect accepted patches: **0**. Average completion output was
273.8 tokens, with P50/P95 wall time of 11.267/12.600 seconds.

The Wilson 95% interval is 23.07%–88.24%. This small result validates the
bounded workflow and two one-shot locked transfers; it is not a broad
code-repair accuracy claim. Agent v0.5.0's 2/3 result remains immutable and is
reported separately because the task sets differ.

## Integrity evidence

- report SHA-256: `fa274cb6a02a0623be780b94ad1286ec3704a29e8e3021a8485350f29af31646`
- terminal ledger SHA-256: `a22b116185f95f74dd8980460764d2fb4433714233823b1b9e1fe38c073b1b3a`
- locked workflow run: `39584933038`
- locked retries: none

The hash chain is tamper-evident after publication; it is not an independently
immutable store.
