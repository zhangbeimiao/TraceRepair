# Function Calling development findings: `0.8.0-dev1.1`

This result is a five-task **known development-set** evaluation. It is not a
locked generalisation result and it does not replace the published
`0.7.0-dev2` six-repository blind result.

## Result

- `3/5 pass@1` (`60%`), with Wilson 95% interval `0.2307–0.8824`;
- `2/5` safe human handoffs;
- `0` incorrect patches accepted;
- `0` Function Calling format-contract failures;
- average completion tokens: `489.6`;
- P50/P95 wall time: `14.906s / 51.234s`.

Compared with the immutable parent `0.8.0-dev1` run, format failures fell from
`5/5` to `0/5` and pass@1 increased from `0/5` to `3/5`. The custom-JSON
development baseline remains `4/5`; therefore native Function Calling improved
the protocol boundary but did not yet improve repair rate on this small set.

## Successful tasks

- `boltons-empty-multireplace`;
- `more-itertools-falsey-validator`;
- `httpie-host-header-offline`.

All three candidates passed both the registered target test and full regression
suite, then stopped at `awaiting_review`.

## Safe handoffs

- `humanize-negative-fraction`: the reviewed excerpt ended before the sign and
  formatting boundary, so the reviewer refused to approve an unverified patch.
- `tqdm-sizeless-bool`: the observed slice did not contain `__bool__` or the
  boolean-casting defect site, so the agent declined to guess.

Neither handoff applied an incorrect accepted patch. These failures point to
insufficient retrieval/read coverage, not Function Calling serialization.

## Integrity

- report SHA-256: `d9b13bec28f9555527654a97d5e9e1fb220a758cb44c8a398bbe7b9acc47842e`;
- terminal ledger record: `dd372b6cf68d7d331ddce4e1265d3cc239676ce51ec8a0260ff94cf6b13f5251`;
- attempts file SHA-256: `bac80d4fdb8d2a99054fc4a56098ef675c9b98582db6022c1aceef036c333d6c`;
- protocol manifest SHA-256: `1c2cf6f03167c5e09a43f069c1e4c145784e22e7854449311d2789b6cab31b46`;
- prompt-security report SHA-256: `afa1e856d793484b714c7f155254c1128120dd81e077d2611b4d429e0d57aa36`.

The task set will not be rerun under this Agent version. Any retrieval, prompt,
or policy change requires a new version and result directory.
