# Milestone 2-10: restricted regression gate

## Decision

`CandidateRepairWorkflow` now follows this fixed verification order:

1. validate and apply an externally supplied diff;
2. run the one allowlisted case test;
3. only if it passes, run the complete EventRelay test suite in that disposable workspace;
4. enter `awaiting_review` only if both runs pass.

Any patch rejection, target-test failure, regression failure, timeout, or runner
error returns the task to `needs_human`. There is no path from a failed target
test to the regression runner.

## Isolation correction found during implementation

The first regression attempt copied the root `tests/` directory into a case
workspace. That directory also contained TraceRepair's own tests, which depend
on project-only modules and are not part of EventRelay. The regression runner
therefore reported irrelevant import errors.

EventRelay tests now live in `eventrelay_tests/`. Materialization copies only
that directory into the case workspace as `tests/`; TraceRepair's infrastructure
tests remain at the project root. This keeps the evaluated repository, its test
surface, and its failure signal aligned.

## Evidence

The verification suite covers all three branches:

- policy-rejected diff: no test run;
- policy-accepted but non-fixing diff: target test runs, regression does not;
- target-passing diff with a separate regression defect: regression runs and
  returns to `needs_human`;
- fully passing diff: reaches `awaiting_review`.

The full project suite currently passes with 58 tests. Temporary pytest state
is explicitly directed to the D: project `tmp/` directory.
