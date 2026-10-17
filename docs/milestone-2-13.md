# Milestone 2.13: deterministic recovery at the diagnosis budget boundary

## Observed failure

The live end-to-end run `model-agent-8360ffff` used all three diagnosis turns
and stopped in `needs_human`. Its trace showed:

1. a broad `EventRelay` search returned ten hits across five files;
2. a refined `parse_event` search still covered two files;
3. the model read `validator.py`, which did not contain the quoted task literal;
4. the controller's zero-token fallback search for `false` found three hits, all
   in `src/eventrelay/config.py`;
5. the loop stopped because the model-turn budget had ended, despite having one
   unambiguous allowlisted source path.

## Root cause

The controller counted model decisions correctly but treated the turn limit as
a hard stop for deterministic tools as well. It failed to distinguish an
uncertain model choice from a mechanically safe action supported by a unique
search result.

## Change

The controller may now read a file without another model request only when all
bounded search hits resolve to exactly one repository-relative path. The path
still passes the read whitelist, the file must contain the task's quoted
literal, and the recovery is persisted as a `deterministic_recovery` event.

This recovery is used in two bounded situations:

- a selected file is irrelevant and a quoted-literal fallback finds one path;
- the final diagnosis turn returns search hits for one relevant path.

## Safety invariants

- no shell or arbitrary command is introduced;
- only `src/eventrelay` and approved docs remain readable;
- zero or multiple candidate paths never trigger automatic reading;
- source relevance is checked before entering patch generation;
- the model still cannot write files or invoke tests;
- candidate diffs still pass policy, target tests, regression, and human review.

## Verification

- 23 focused planner, read-tool, patch, and end-to-end tests passed;
- 60 remaining project tests passed;
- the regression suite includes the exact three-turn budget-boundary trace shape.

This is a useful interview example because the fix improves completion rate by
moving a deterministic decision out of the LLM while preserving the original
security boundary.
