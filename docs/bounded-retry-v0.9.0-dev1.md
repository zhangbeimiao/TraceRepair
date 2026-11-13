# `0.9.0-dev1`: bounded clean-snapshot retry

`0.9.0-dev1` is a development-only verification runtime for a controlled second
candidate. It does **not** change any frozen one-shot benchmark result.

For each candidate, the controller creates a new disposable workspace from a
hash-verified fault snapshot. A target-test assertion failure or a candidate
syntax error may produce one bounded feedback object and trigger candidate two.
The failed workspace remains as evidence but is never used as candidate two's
input. Policy rejection, timeouts, environment errors, checkpoint/hash
conflicts, regression failures, and any second candidate failure stop at
`needs_human`.

Each durable attempt record contains its index, source-snapshot hash, workspace
hashes, candidate Diff hash, model counters, test summaries, feedback, stop
reason, and elapsed time. An interrupted run with an incomplete active attempt
fails closed; an interruption after a completed failed attempt resumes at the
next attempt without replaying the first candidate.

Run the deterministic controller demonstration with:

```powershell
& .\.venv\Scripts\python.exe scripts\bounded_retry_demo.py
```

It makes zero model-provider requests and proves the clean-snapshot property on
an EventRelay target: candidate one is policy-valid but fails the target test;
candidate two starts from the original snapshot and reaches `awaiting_review`.
The next milestone is to attach this bounded runtime to the frozen Function
Calling planner configuration and evaluate only on development tasks.
