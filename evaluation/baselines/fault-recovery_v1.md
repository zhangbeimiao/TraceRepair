# TraceRepair fault-injection evidence: recovery_v1

Offline crash-recovery and deterministic state-machine invariant evidence.

## Summary

- Scenarios: **10**
- Passed: **10**
- Failed: **0**
- Provider requests: **0**
- Total test time: **30.786 seconds**

## Scenarios

| Scenario | Category | Result | Seconds | Enforced invariants |
|---|---|---:|---:|---|
| crash_after_source_read | crash_recovery | PASS | 3.72 | verified source checkpoint resumes without repeating search or read; only the not-yet-completed model patch decision is requested |
| crash_after_patch_applied | crash_recovery | PASS | 3.385 | resume performs zero model calls; patch is applied at most once; target and regression gates still execute |
| crash_after_target_passed | crash_recovery | PASS | 3.599 | resume performs zero model calls; patch and target test are not repeated; regression remains mandatory before awaiting_review |
| patched_workspace_tampered | integrity_conflict | PASS | 2.268 | workspace hash conflict transitions to needs_human; model and tests are not started after the conflict |
| source_artifact_tampered | integrity_conflict | PASS | 2.22 | source artifact hash conflict transitions to needs_human; model and patch application are not started |
| patch_committed_before_phase_marker | write_ordering | PASS | 4.27 | durable tool result is reconciled with a stale phase marker; patch is not applied twice |
| policy_rejection_blocks_tests | state_machine_invariant | PASS | 2.03 | a policy-rejected patch cannot start target or regression tests |
| target_failure_blocks_regression | state_machine_invariant | PASS | 2.612 | a failed target test cannot start regression |
| regression_failure_blocks_review | state_machine_invariant | PASS | 3.37 | a failed regression cannot enter awaiting_review |
| all_gates_required_for_review | state_machine_invariant | PASS | 3.312 | awaiting_review requires accepted patch, passing target, and passing regression |

## Claim boundary

These deterministic tests demonstrate the listed recovery and transition invariants for the exercised crash windows; they are not a proof against arbitrary hardware, filesystem, SQLite, or operating-system failures.
