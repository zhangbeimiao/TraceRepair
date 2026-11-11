# TraceRepair baseline: locked_v1

Three new repositories, one locked attempt per independent historical bug; no retry or post-reveal policy change.

## Summary

- Observed runs: **3**
- Independent bugs: **3**
- Repeated runs: **0**
- Successful runs: **2**
- `needs_human`: **1**
- Average completion tokens: **414.33**
- Average model calls: **3**
- Average wall seconds: **14.927**
- Estimated cost: **None**

## Runs

| Bug | Agent | Status | Success | Tokens | Calls | Seconds | Target | Regression | Diff | Stop reason |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| function_rag_locked:jaraco-text-headless-camel | 0.8.0 | awaiting_review | True | 454 | 3 | 13.047 | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| function_rag_locked:sortedcontainers-empty-extend | 0.8.0 | awaiting_review | True | 657 | 4 | 21.157 | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| function_rag_locked:structlog-missing-event | 0.8.0 | needs_human | False | 132 | 2 | 10.578 | False | False | not_preserved_in_source_evidence | The provided slice of src/structlog/dev.py (lines 80-190) ends before ConsoleRenderer.__call__, so the code that reads event_dict["event"] and raises KeyError is not visible; I cannot produce an exact, minimal diff without altering unseen behavior. |

## Failure reasons

- 1 × The provided slice of src/structlog/dev.py (lines 80-190) ends before ConsoleRenderer.__call__, so the code that reads event_dict["event"] and raises KeyError is not visible; I cannot produce an exact, minimal diff without altering unseen behavior.

## Limitations

- Evidence replay makes no provider request and does not rerun a locked task.
- Missing latency, cost, or Diff fields remain null rather than inferred.
- Observed-run success rate is not an independent-bug accuracy estimate.
- A provider model identifier is frozen, but no provider weight digest was available.
