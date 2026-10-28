# Source refinement: Agent 0.8.1-dev1

The frozen 0.8.0 locked `structlog-missing-event` attempt read `dev.py` lines
80–190. The target `ConsoleRenderer.__call__` begins at line 191 and the
`event_dict.pop("event")` operation is at line 218. The model handed off
without proposing a patch. This historical locked outcome is unchanged.

In the new development runtime, the native patch planner may explicitly request
one additional `read_file` call for a different range of the same confirmed
source file, provided the diagnosis turn budget remains. The host enforces the
existing path and 200-line limits, rejects repeated or different-path reads,
stores an audit event, persists the new source checkpoint, and does not expose
additional execution permissions. SQLite records that the extra read was used;
resuming cannot silently reset the allowance. Model call and token limits still
apply, and ordinary handoff remains available.

The known structlog task is now **development data**, not a new blind test.
Offline tests replay a fixed read sequence without model calls and include
repeated, different-path, and excessive-range cases. In one live development
run, the model used the extra read for structlog and passed the configured
tests; the three-case development cohort achieved 2/3. This is evidence of
the feature being exercised, not proof of a general improvement. The full
results and the remaining tqdm failure are in
`evaluation/results/source-refinement-v0.8.1-dev1/DEVELOPMENT_FINDINGS.md`.
Future locked evidence must use previously unused repositories and a new frozen
configuration.

To run the three known development cases after configuring local provider
environment variables:

```powershell
& .\.venv\Scripts\python.exe scripts\run_benchmark.py --manifest evaluation\benchmarks\source-refinement-v0.8.1-dev1.json --split development
```

The benchmark permits up to 15 model calls in total. It writes a new ledger;
the existing `function-rag-locked-v0.8.0` evidence is never reopened or changed.
