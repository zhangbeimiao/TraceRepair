# `0.7.0-dev2` development findings

This directory freezes the same five **known development tasks** used by
`langgraph-migration-v0.7.0-dev1`. It measures whether one bounded semantic-review
step addresses observed candidate-quality failures. It is not a held-out or blind
generalisation result.

## Result

- Agent: `0.7.0-dev2`
- Model: `qwen3.8-flash`
- Protocol: strict `pass@1`
- Oracle preflight: all five buggy revisions failed their target test and all five
  historical fixed revisions passed target plus regression tests
- Outcome: `4/5` passed; one candidate failed its registered target test and was
  handed to a human
- Incorrect accepted patches: `0`
- Average completion tokens: `543.2`
- P50 / P95 wall time: `14.329s` / `18.391s`
- Wilson 95% interval: `37.55%` to `96.38%`

Compared with `0.7.0-dev1` on the same task identities, pass@1 moved from `2/5`
to `4/5`, while average completion tokens moved from `315.6` to `543.2` and P50
wall time moved from `9.985s` to `14.329s`. With only five known tasks, this is
mechanism evidence rather than a statistically reliable accuracy claim.

## Preserved failure

`tqdm-sizeless-bool` produced a policy-valid candidate that added `__bool__` and
returned `True` when `len(self)` raised `TypeError`. The semantic reviewer returned
the candidate unchanged. The deterministic patcher applied it to the disposable
workspace, but `tqdm/tests/tests_tqdm.py::test_bool` exited with code `1` after
`702ms`. Regression tests were never started and the task moved to `needs_human`.

Audit artifacts:

- `failures/tqdm-sizeless-bool.diff`: exact reviewed candidate
- `failures/tqdm-sizeless-bool.json`: candidate, review, target-test and handoff
  digests copied from the SQLite trace
- `logs/tqdm-sizeless-bool.log`: bounded runner summary
- `attempts.jsonl`: append-only SHA-256 ledger containing every start and finish
- `report.json` and `report.json.sha256`: complete report and byte-level checksum

The failure is deliberately retained. Any attempt to improve it must use a new
Agent version and a new benchmark identifier; it must not rewrite this cohort.

## Integrity and claim boundary

The ledger contains ten verified records: one start and one finish for each task.
The terminal record is
`9811b87f769acb6b8b9210f60653f7f46d5cb975d5f196da02a6627d90dc83cd`.
The report file SHA-256 is
`21f6483aa613aa8f875f2eda4cb3d095cbcd8303349027799ec4fe7d10b46c53`.

These hashes make later changes detectable once published. They do not turn Git
or GitHub into an immutable store, and this development run must not be described
as a locked benchmark.
