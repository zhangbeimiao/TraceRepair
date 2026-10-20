# Development findings: historical-python-v0.7.2

Both development tasks reached patch generation after the deep-source read fix, but both candidate
diffs were rejected with `PATCH_CONTEXT_MISMATCH`. The safety gate was not relaxed.

Inspection showed that the model received a mid-file source slice without its absolute repository
line range. This allowed syntactically plausible diffs whose hunk headers were relative to the
slice. Agent `0.4.0-dev3` adds the absolute line range to the patch evidence and records each raw
candidate diff as a SHA-256-addressed audit artifact before applying it.

- terminal ledger hash: `e07fa78f12405f41218a8df2806d295ddff0c4079a27e232f1d92a5e94fea002`
- report SHA-256: `b19dc2d9a149915b958b2136af0248841f2cbd2a7451ce3407997415de7c3698`
- development result: 0/2 pass@1
- locked split: not opened

These are valid development failures and remain published rather than being deleted or overwritten.
