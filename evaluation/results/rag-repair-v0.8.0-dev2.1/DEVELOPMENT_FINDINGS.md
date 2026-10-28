# Code RAG repair findings: `0.8.0-dev2.1`

This is a five-task **known development-set** evaluation. It measures the
end-to-end effect of the retrieval candidate that already passed the separate
Recall@K/MRR activation gate. It is not locked generalisation evidence and it
does not replace the published `0.7.0-dev2` blind result.

## Result

- `3/5 pass@1` (`60%`), with Wilson 95% interval `0.2307–0.8824`;
- `2/5` safe human handoffs;
- `0` incorrect patches accepted;
- average completion tokens: `473.6`;
- P50/P95 wall time: `14.828s / 18.906s`.

The no-RAG native Function Calling parent (`0.8.0-dev1.1`) also achieved
`3/5`. Therefore this small development set does **not** show a repair-rate
gain. It does show lower average completion tokens (`489.6 → 473.6`, `-3.27%`)
and a lower P95 wall time (`51.234s → 18.906s`, `-63.10%`). Those efficiency
changes are descriptive measurements on five known tasks, not broad latency
claims.

## Successful tasks

- `humanize-negative-fraction`;
- `boltons-empty-multireplace`;
- `more-itertools-falsey-validator`.

All three candidates passed the registered target test and full regression
suite, then stopped at `awaiting_review`.

## Safe handoffs

- `tqdm-sizeless-bool`: retrieval identified `tqdm/_tqdm.py`, but the model's
  requested source slice still omitted the `__bool__` implementation. The
  agent refused to invent an edit.
- `httpie-host-header-offline`: RAG ranked
  `httpie/models.py::HTTPRequest.headers` first and the model proposed the
  semantically relevant one-line change. Its hunk header was malformed
  (`@@ 80,6 +80,7 @@`, missing the required old-range `-` and with inconsistent
  counts), so the deterministic parser returned `PATCH_PARSE_ERROR`. No file
  was modified and no test was started.

The HTTPie failure is retained as evidence that retrieving the correct symbol
does not grant execution authority and does not make malformed model output
acceptable. Any future conservative Diff canonicalisation must use a new Agent
version and a new evaluation result.

## Retrieval evidence

On the same five known development tasks, file-level hybrid retrieval improved
Recall@3 from `0.80` to `1.00` and MRR from `0.75` to `0.80`, while Recall@5
remained `1.00`. This justified activating retrieval for development, but the
end-to-end result above shows why retrieval metrics and repair metrics must be
reported separately.

## Integrity

- benchmark manifest SHA-256: `dc77caee3deb13078820092b585e175229f3650376fd511b184b7fe6f0e799f3`;
- manifest lock SHA-256: `0f1c7570f21943ca1284276d87f8215b67db8651472ffdd3bf15eb699b84bb41`;
- report file SHA-256: `8586e75b2ac325e078a15de105e6da6743cf747bb5ef5fd626dd55e69b9330f5`;
- terminal ledger record: `c5fdd257e6e68d9fe4387f27de81e65d21c0251c2e84d6a78b4cd2b3cc1c2219`;
- attempts file SHA-256: `a6c7b586c8e7c26db917a427aec36dc43ea08f76cb639318a0cb8883dd6feb5f`;
- semantic retrieval report SHA-256: `1da646921d0a7667e0a9336043856ee9132f88abffe3bc282623b23e0fd51b3d`;
- retrieval activation decision SHA-256: `07a963285e46182fde1dbc04544a7bf4739218e36382d250d4a8c7d5fdbcee6c`;
- rejected HTTPie candidate SHA-256: `83ea89983c002526ce7746360a2856338187d3efe4403d7973ddfc0e3de6c86f`.

This task set will not be rerun under `0.8.0-dev2.1`. The next valid repair
measurement must use frozen `0.8.0` configuration on previously unused locked
repositories, with every success and failure published.
