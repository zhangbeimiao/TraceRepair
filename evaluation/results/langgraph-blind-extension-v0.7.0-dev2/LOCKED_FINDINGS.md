# `0.7.0-dev2` second locked blind cohort

This directory freezes a second cohort of three previously unused repositories.
The task definitions and `0.7.0-dev2` runtime were committed and pushed before
any provider request. Each task ran once, no failure was retried, and every
outcome is retained.

## Result

- Agent: `0.7.0-dev2`
- Model: `qwen3.8-flash`
- Protocol: strict locked `pass@1`
- Repositories: cachetools, python-slugify and Click
- Oracle preflight: `3/3` buggy revisions failed their target; `3/3` historical
  fixed revisions passed target and regression
- Outcome: `1/3` passed; `2/3` safely handed off to a human
- Incorrect accepted patches: `0`
- Average completion tokens: `376.33`
- P50 / P95 wall time: `9.032s` / `14.156s`
- Wilson 95% interval: `6.15%` to `79.23%`

## Successful repair

`python-slugify-invalid-types` produced a candidate that passed patch policy,
the registered target test and the complete registered regression suite. The
exact Diff and hashed verification evidence are retained under `successes/`.
The final state remained `awaiting_review`; no automatic merge occurred.

## Preserved safe stops

`cachetools-falsey-getsizeof` and `click-sentinel-copy` both completed bounded
search and source reading. Their patch-generation responses violated the
structured `reason` contract. The deterministic controller stopped before a
candidate Diff existed, before a workspace write, and before tests. The trace
therefore contains a response hash and parse error rather than a fabricated
"failed Diff". Both records are retained under `failures/`.

## Integrity and claim boundary

- Preflight seal SHA-256:
  `33393bbe7536e13393ae0f0b14d4c0d91033768d3473018268f40907621ea2d3`
- Manifest SHA-256:
  `cc0dce72e5e963d634223016477c12188a4a84eee71ba7bd77cc490b72322a2e`
- Report file SHA-256:
  `031ce93c4f2bdea654374990b099f14fa9fec3c8dc87062cd63259a22f4fbaf2`
- Terminal ledger record:
  `50bb8391f922a98d1ceb31cf3aeaf4882a695a7317838c1fd92da084749f9b52`

Together with the first sealed blind cohort, the public blind evidence now
contains six repositories and reports `2/6` pass@1, `4/6` safe human handoffs,
and zero incorrect accepted patches. Six tasks still do not establish a
universal repair rate. Any attempt to improve these failures requires a new
Agent version and a new benchmark identifier; this cohort must not be rerun.
