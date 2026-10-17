# Milestone 2.4: instrumented tool traces

`InstrumentedTools` wraps repository reads and target-test runs for a task in
the `running` state. Every invocation emits `tool_started`, `tool_finished`,
and `checkpoint_saved` events to the D-drive SQLite database.

Trace payloads preserve parameters, outcome, error code, timing, result counts,
paths, and SHA-256 digests. They intentionally omit source bodies and raw test
output. The returned tool result still contains the bounded content the caller
needs, while checkpoint state remains small enough to resume a task safely.

The test runner also sets `TMP` and `TEMP` to a `.tmp` directory inside the
case workspace. Project SQLite files, pip cache, workspaces, and temporary test
artifacts therefore remain on D drive.

The next deterministic milestone can define the workflow controller: it will
choose a legal next tool call from task state without involving an LLM.
