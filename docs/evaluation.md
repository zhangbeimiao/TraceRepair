# Evaluation protocol

The ten EventRelay cases are evaluation tasks, not model-training examples.
Each begins from the reference implementation plus exactly one bug-injection
patch. A reference fix is deliberately not stored in a case workspace.

## Split

Development cases: 01, 03, 05, 07, 10.

Locked cases: 02, 04, 06, 08, 09. Do not tune prompts, tool descriptions, or
retrieval settings after inspecting locked-case source, oracle, or outcome.

## Per-run record

Record the case ID, baseline revision hash, model and prompt version, tool
calls, candidate diff hash, target-test result, regression result, elapsed
time, token usage, and stop reason. Run each locked case three times under the
same configuration; report raw outcomes as well as aggregate counts.

## Success criteria

A case is repaired only when the target test and the full regression suite pass
and the diff changes only permitted source paths. A target-test pass followed
by a regression failure is `NEEDS_HUMAN`, not success.
