# LangGraph development comparison: `0.7.0-dev1` vs `0.7.0-dev2`

Both cohorts use the same five known development-task identities. `0.7.0-dev2`
adds one bounded semantic-review node between patch generation and deterministic
application. This is an ablation-style development comparison, not a fresh blind
benchmark.

| Metric | `0.7.0-dev1` | `0.7.0-dev2` | Change |
|---|---:|---:|---:|
| pass@1 | 2/5 (40%) | 4/5 (80%) | +2 tasks / +40 pp |
| Human handoffs | 3 | 1 | -2 |
| Incorrect accepted patches | 0 | 0 | unchanged |
| Average completion tokens | 315.6 | 543.2 | +227.6 (+72.1%) |
| P50 wall time | 9.985s | 14.329s | +4.344s (+43.5%) |
| P95 wall time | 16.094s | 18.391s | +2.297s (+14.3%) |

## Interpretation

The review node recovered two additional tasks while preserving zero incorrect
accepted patches. The trade-off was one extra model call on reviewed paths, 72.1%
more average completion tokens, and 43.5% higher median wall time.

The sample is too small to establish statistical superiority. The `0.7.0-dev2`
Wilson 95% interval is 37.55% to 96.38%, and all tasks were already visible during
development. Therefore the result supports only this statement:

> On the same five known development tasks, the bounded semantic-review mechanism
> improved observed pass@1 from 2/5 to 4/5 while deterministic target tests still
> rejected the remaining incorrect candidate.

It does not support an 80% general code-repair claim.

## Remaining failure

For `tqdm-sizeless-bool`, the draft added a `__bool__` method that converted a
`TypeError` from `len(self)` into `True`. The reviewer returned it unchanged. The
candidate passed path, size and exact-context gates but failed the registered target
test. The controller stopped before regression and handed the task to a human.

The exact Diff and structured failure evidence are retained under
`evaluation/results/langgraph-review-offline-v0.7.0-dev2/failures/`.

## Next protocol

`0.7.0-dev2` is now frozen as development evidence. The next credible measurement
must use repository-disjoint tasks that were not used to design or debug the review
node. Agent configuration and task manifests must be frozen before those locked
tasks run, and each locked task may be attempted only once.
