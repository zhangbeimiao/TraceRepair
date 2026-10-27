# `0.7.0-dev2` locked blind findings

This directory freezes three previously unused repositories selected and sealed
before any provider request. All three tasks used the exact preregistered Agent,
prompt, model, policy and oracle configuration. Each task ran once; no failed task
was retried and every outcome is retained.

## Result

- Agent: `0.7.0-dev2`
- Model: `qwen3.8-flash`
- Protocol: strict locked `pass@1`
- Repositories: toolz, prettytable and glom; none appeared in the development cohort
- Oracle preflight: every buggy revision failed its target test; every historical
  fixed revision passed its target and regression tests
- Outcome: `1/3` passed; two tasks safely handed off to a human
- Incorrect accepted patches: `0`
- Average completion tokens: `533.67`
- P50 / P95 wall time: `14.718s` / `16.265s`
- Wilson 95% interval: `6.15%` to `79.23%`

## Successful repair

`toolz-empty-interpose` produced a candidate that passed patch policy, its registered
target test and the complete registered regression suite. The final state was
`awaiting_review`; TraceRepair did not merge the change automatically.

## Preserved safe stops

`prettytable-horizontal-align` generated and reviewed a policy-valid Diff. The
target test passed, but the broader registered regression suite exited with code
`1`. The deterministic controller stopped at `needs_human`; the candidate was not
accepted. The exact candidate and hashed test evidence are in `failures/`.

`glom-path-index-boundary` generated a draft candidate, but the semantic-review
response violated the structured `reason` contract. The controller rejected that
response before applying the candidate or starting tests. The draft Diff and the
hashed parse-error evidence are retained in `failures/`.

## Integrity and claim boundary

- Preflight seal SHA-256:
  `42fda4daa06d9261a452a78d7f9485c82ab85fbfcf3de42a6fe2ab4668b0251c`
- Manifest SHA-256:
  `fda36a88b38f7dca2e5b035a0736088daa8c0fe04db78ffd1a2294acbbf7f842`
- Report file SHA-256:
  `001301c7cf90954d3d6e7485b46d1fcc6783e0c7d6f7499d85ce60a43dd4293e`
- Terminal ledger record:
  `17ba3faac4a6182c121215e006a760f0fb4280524774025ed156743b8cb3188a`

These hashes make later changes detectable after publication; they do not make Git
an immutable store. The sample contains only three bugs. It demonstrates honest
one-shot transfer and failure containment, not a 33% universal repair rate. Any
change intended to improve either failure requires a new Agent version and a new
benchmark identifier; these tasks must not be rerun under `0.7.0-dev2`.
