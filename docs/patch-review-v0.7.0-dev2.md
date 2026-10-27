# Bounded semantic patch review (`0.7.0-dev2`)

`0.7.0-dev2` adds exactly one LangGraph node between patch generation and deterministic
application:

```text
generate_patch -> review_patch -> apply_patch -> run_target -> run_regression
```

The motivation comes from the frozen `0.7.0-dev1` migration regression. Three candidates were
syntactically valid and policy-compliant but failed the registered target test because they changed
the wrong semantic boundary. This was not a graph-routing or SQLite-recovery failure.

## Authority boundary

The reviewer receives only the issue, the confirmed source slice, and the draft unified diff. It may
return one reviewed unified diff or request human handoff. It cannot call tools, read additional
files, write the workspace, run shell commands or tests, alter task status, or accept a repair.

Both the draft and reviewed candidate are stored as content-addressed artifacts. The trace records
their SHA-256 digests and whether the reviewer changed the draft. Only the reviewed candidate enters
the existing deterministic gates:

1. path and diff policy;
2. exact/unique patch-context matching;
3. registered target test;
4. full regression suite;
5. human review.

The graph still compiles without a LangGraph checkpointer. SQLite `TraceStore` remains the sole
durable source for budgets, state transitions, tool results, candidate evidence, and recovery.

## Budget and recovery

- model calls: at most 5 per task;
- completion budget: at most 3,072 tokens per task;
- semantic reviews: exactly one at most;
- patch attempts: exactly one;
- verification-only resume after a durable patch application: zero model calls.

## Evaluation rule

The frozen `0.7.0-dev1` result remains `2/5 pass@1` with three safe rejections. `0.7.0-dev2` uses the
new benchmark id `langgraph-review-offline-v0.7.0-dev2`; no predecessor attempt is overwritten or retried.
The five tasks are known development tasks, so this benchmark measures whether the review mechanism
addresses observed failure modes. It is not a fresh generalization claim.

## Frozen development result

The deterministic offline cohort completed at `4/5 pass@1`, compared with `2/5` for
`0.7.0-dev1` on the same task identities. Incorrect accepted patches remained at zero. Average
completion tokens increased from `315.6` to `543.2`, and P50 wall time increased from `9.985s`
to `14.329s`.

The remaining `tqdm-sizeless-bool` candidate was returned unchanged by the reviewer, applied only
to the disposable workspace, and rejected by its target test. Its exact Diff, trace digests and
stop reason are preserved in the benchmark result directory. See
[`langgraph-dev1-vs-dev2.md`](langgraph-dev1-vs-dev2.md) for the bounded comparison and claim
limits.

An earlier development run under `langgraph-review-v0.7.0-dev2` is retained for audit, but its HTTPie
oracle called `httpbin.org` and was found to be network-dependent on a later preflight. It is therefore
superseded for comparison purposes, not deleted or silently rewritten.
