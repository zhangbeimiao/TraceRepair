# Milestone 2.9: bounded regression verification

`run_regression` has no caller-controlled selector. It always runs the case
workspace's `tests/` directory with the same timeout, local environment, and
bounded output policy as target tests.

The candidate loop only invokes regression after a target test passes. A
regression failure returns the task to `needs_human`; only two passing stages
lead to `awaiting_review`.
