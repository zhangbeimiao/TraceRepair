# Milestone 2.14: align model patch parsing with the enforced diff contract

## Observed failure

Live task `model-agent-aab74d1d` successfully recovered from an irrelevant
source file, read `src/eventrelay/config.py`, and reached patch generation. The
fourth model response was rejected before patch application with `model proposed
an invalid patch`. The response used 171 completion tokens; no source mutation
or test execution occurred.

## Root cause

The planner accepted only a diff whose first line was `--- a/...`, while both
the patch policy and patch applier already supported the standard Git form that
starts with `diff --git a/... b/...`. The three layers therefore disagreed on
their format contract.

## Change

The planner now accepts and normalizes only these equivalent unified-diff forms:

- `--- a/<path>` as the first line;
- a standard `diff --git a/<path> b/<path>` preamble followed by `--- a/<path>`;
- either form inside one Markdown code fence.

Every accepted candidate must still contain `--- a/`, `+++ b/`, and an `@@`
hunk. `*** Begin Patch`, prose-prefixed output, oversized output, missing
headers, and non-string values remain denied.

Invalid model responses now record a safe parser error category and a SHA-256
of the response content. The raw model output is not persisted.

## Verification

- 24 focused planner, patch-policy, patch-application, and end-to-end tests passed;
- 14 model-workflow, transport, instrumentation, and trace-store tests passed;
- the live runner now prints its task id even when the planner stops safely.

This repair improves provider-format tolerance without changing writable paths,
test gates, shell restrictions, or human-review requirements.
