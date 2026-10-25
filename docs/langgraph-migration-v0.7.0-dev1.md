# LangGraph migration: Agent 0.7.0-dev1

## Scope

`0.7.0-dev1` replaces the production entrypoint's monolithic Python controller
with an explicit LangGraph state machine. The graph contains these nodes:

```text
diagnose (bounded loop)
  -> checkpoint_source
  -> generate_patch
  -> apply_patch
  -> run_target
  -> run_regression
```

`resume` is a separate entry router. It reads the verified recovery phase from
SQLite and continues at `generate_patch`, `run_target`, or `run_regression`.

LangGraph is compiled without a checkpointer. Its state exists only during one
process invocation. SQLite remains the only durable source for task status,
model budget, tool events, recovery phase, and artifact hashes.

## Compatibility evidence

The automated tests cover the complete successful path and a process crash
immediately after patch persistence. The recovery test proves that the resumed
graph makes zero model calls, does not apply the patch twice, and continues
through target and regression tests.

The historical `0.6.0 / historical-python-v1.1.3` evidence is immutable. It is
not relabelled as evidence for this migration.

## Migration regression protocol

`evaluation/benchmarks/langgraph-migration-v0.7.0-dev1.json` contains five
previously known historical tasks. All are labelled `development`; this is an
architecture-regression comparison, not a fresh locked-set generalisation
claim. Oracle preflight succeeds for all five tasks on the supported local
environment.

Run the model-backed comparison once with:

```powershell
& .\.venv\Scripts\python.exe scripts\run_benchmark.py `
  --manifest evaluation\benchmarks\langgraph-migration-v0.7.0-dev1.json `
  --split development
```

Before a `0.7.0` release, create a separate benchmark containing new repositories,
freeze the agent configuration after development, and execute each new locked
task exactly once.
