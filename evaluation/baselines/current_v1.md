# TraceRepair baseline: current_v1

Current-agent evidence on three previously observed development bugs; not locked and not a generalization claim.

## Summary

- Observed runs: **3**
- Independent bugs: **3**
- Repeated runs: **0**
- Successful runs: **1**
- `needs_human`: **2**
- Average completion tokens: **524**
- Average model calls: **3.67**
- Average wall seconds: **11.771**
- Estimated cost: **None**

## Runs

| Bug | Agent | Status | Success | Tokens | Calls | Seconds | Target | Regression | Diff | Stop reason |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| refinement_budget_development:structlog-missing-event | 0.8.5-dev1 | needs_human | False | 197 | 3 | 7.234 | False | False | not_preserved_in_source_evidence | The target test file tests/test_tracerepair_missing_event.py is not registered/observable and the source slice omits the exact `event_dict.pop("event")` line number, so I cannot confirm the intended missing-event rendering contract (e.g. empty string vs. a sentinel) or produce an exact diff with verified context lines. |
| refinement_budget_development:tqdm-sizeless-bool | 0.8.5-dev1 | needs_human | False | 653 | 5 | 13.641 | False | False | preserved | candidate patch failed target test: TEST_FAILED |
| refinement_budget_development:httpie-host-header-offline | 0.8.5-dev1 | awaiting_review | True | 722 | 3 | 14.438 | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |

## Failure reasons

- 1 × The target test file tests/test_tracerepair_missing_event.py is not registered/observable and the source slice omits the exact `event_dict.pop("event")` line number, so I cannot confirm the intended missing-event rendering contract (e.g. empty string vs. a sentinel) or produce an exact diff with verified context lines.
- 1 × candidate patch failed target test: TEST_FAILED

## Limitations

- Evidence replay makes no provider request and does not rerun a locked task.
- Missing latency, cost, or Diff fields remain null rather than inferred.
- Observed-run success rate is not an independent-bug accuracy estimate.
- A provider model identifier is frozen, but no provider weight digest was available.
