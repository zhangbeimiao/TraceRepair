# TraceRepair baseline: portfolio_v1

Legacy EventRelay, public repository repeat-stability, and held-out repository evidence. This is not a current-agent accuracy claim.

## Summary

- Observed runs: **19**
- Independent bugs: **11**
- Repeated runs: **8**
- Successful runs: **19**
- `needs_human`: **0**
- Average completion tokens: **213.11**
- Average model calls: **3**
- Average wall seconds: **None**
- Estimated cost: **None**

## Runs

| Bug | Agent | Status | Success | Tokens | Calls | Seconds | Target | Regression | Diff | Stop reason |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| eventrelay:01 | 0.4.0-dev1 | awaiting_review | True | 263 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:03 | 0.4.0-dev1 | awaiting_review | True | 173 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:07 | 0.4.0-dev1 | awaiting_review | True | 219 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:10 | 0.4.0-dev1 | awaiting_review | True | 176 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:01 | 0.4.0-dev1 | awaiting_review | True | 261 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:03 | 0.4.0-dev1 | awaiting_review | True | 186 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:07 | 0.4.0-dev1 | awaiting_review | True | 247 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:10 | 0.4.0-dev1 | awaiting_review | True | 176 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:02 | 0.4.0-dev1 | awaiting_review | True | 263 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:04 | 0.4.0-dev1 | awaiting_review | True | 207 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:06 | 0.4.0-dev1 | awaiting_review | True | 217 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:08 | 0.4.0-dev1 | awaiting_review | True | 309 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| eventrelay:09 | 0.4.0-dev1 | awaiting_review | True | 220 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| public_repository_repeat:mini-repo-discount | 0.4.0-dev1 | awaiting_review | True | 175 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| public_repository_repeat:mini-repo-discount | 0.4.0-dev1 | awaiting_review | True | 178 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| public_repository_repeat:mini-repo-discount | 0.4.0-dev1 | awaiting_review | True | 175 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| public_repository_repeat:mini-repo-discount | 0.4.0-dev1 | awaiting_review | True | 187 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| public_repository_repeat:mini-repo-discount | 0.4.0-dev1 | awaiting_review | True | 183 | 3 | None | None | None | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |
| heldout_repository_one_shot:heldout-repository-balance | 0.4.0-dev1 | awaiting_review | True | 234 | 3 | None | True | True | not_preserved_in_source_evidence | candidate patch passed target and regression tests; human review required |

## Failure reasons

- None recorded

## Limitations

- Evidence replay makes no provider request and does not rerun a locked task.
- Missing latency, cost, or Diff fields remain null rather than inferred.
- Observed-run success rate is not an independent-bug accuracy estimate.
- A provider model identifier is frozen, but no provider weight digest was available.
