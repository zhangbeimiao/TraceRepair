# Historical benchmark protocol

TraceRepair's historical benchmark measures bounded `pass@1` repair attempts. It is designed
to preserve failures and make post-hoc result editing detectable. It does not claim that a local
JSON file is an immutable or independently trusted store.

## Case construction

Each task must identify a public repository, a full 40-character buggy commit, and the full
commit that fixed the bug. The repository snapshot contains the source from immediately before
the fix and the regression test introduced or changed by the fix. Task configuration, repository
contents, Agent version, model ID, target test, and regression selector are frozen before the
first provider request.

Development and locked tasks are separated by repository. Prompt, policy, or workflow changes
may use only development results. Once a locked task has been attempted, it is never rerun for
the same benchmark ID. Any change to the manifest or Agent requires a new benchmark ID and a new
unseen locked set.

## Success and failure

A task succeeds only when the candidate patch passes both its target test and configured
regression suite and reaches `awaiting_review` or `succeeded`. `needs_human`, invalid model output,
policy rejection, patch mismatch, test failure, process failure, and timeout are all retained as
failures. The runner does not perform best-of-N selection.

Provider and common cloud credential variables are removed from the pytest subprocess. This is
credential hygiene, not a sandbox: repository tests still run with the host user's filesystem and
network permissions, so this benchmark remains limited to operator-approved repositories.

## Evidence chain

Before execution, the runner computes SHA-256 digests for the raw manifest, every task config,
and every materialized repository tree. Each attempt is appended to `attempts.jsonl` with the
previous record hash. The chain is verified before any new append. `report.json` includes every
attempt and the terminal chain hash, and `report.json.sha256` covers the exact report bytes.

This is **tamper-evident after the terminal hash has been published**, not tamper-proof: a local
operator who controls all files could rewrite the ledger and recompute every hash. Publishing the
terminal hash in Git history or a release makes later silent rewriting detectable.

## Metrics

The generated report includes:

- `pass@1` and a Wilson 95% confidence interval;
- human handoffs and incorrectly accepted patches;
- target and regression outcomes for every attempt;
- P50/P95 wall-clock latency;
- model calls, completion tokens, tool calls, and failures;
- a completion-token-only cost estimate when pricing is declared in the manifest;
- every stop reason, including provider and process failures.

Prompt-token cost is not yet recorded and is explicitly excluded from the v0.7 cost estimate.

## Oracle preflight

Before any provider request, the runner creates disposable D: workspaces and verifies that each
buggy snapshot fails the registered target with pytest exit code 1. It separately verifies the
pinned fixed snapshot passes both the target and configured regression suite. Collection errors,
missing dependencies, timeouts, archive checksum mismatches, and unexpectedly passing buggy
snapshots reject the benchmark. Oracle workspaces are removed after validation and their source is
never included in model context.

## Running

Keep repositories and caches under the D: project directory. First validate without provider
calls. On a fresh clone, materialize the three pinned source snapshots first; this verifies each
downloaded archive checksum and does not execute repository code:

```powershell
python scripts\prepare_historical_benchmark.py --download
```

Then run the provider-free benchmark preflight. This executes the approved repository tests in
disposable workspaces but makes no model request and writes no benchmark result:

```powershell
python scripts\run_benchmark.py `
  --manifest evaluation\benchmarks\historical-python-v1.0.0.json `
  --split development `
  --dry-run
```

Then run every pending development task exactly once:

```powershell
python scripts\run_benchmark.py `
  --manifest evaluation\benchmarks\historical-python-v1.0.0.json `
  --split development
```

The locked split is invoked exactly once only after the development result and frozen Agent
configuration have been reviewed.

Re-running the command does not repeat recorded tasks. It verifies the ledger and regenerates the
report from the complete attempt history.

## Invalidated infrastructure runs

Provider, credential, and runner failures remain in their original hash-chained
ledger. They are never deleted or replaced by a retry under the same benchmark ID.
If a pre-model infrastructure fault invalidates a development run, the reason and
original terminal hashes are published, a new benchmark ID is frozen, and the
locked split remains untouched until the replacement development run is reviewed.
