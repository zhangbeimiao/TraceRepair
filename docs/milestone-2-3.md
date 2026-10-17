# Milestone 2.3: bounded target-test runner

`RestrictedTestRunner` accepts only EventRelay selectors in this form:

```text
tests/test_repair_targets.py
tests/test_repair_targets.py::test_case_01_example_name
```

The selector is verified before subprocess creation. The runner invokes Python
with an argument list, `shell=False`, a case-local working directory, an
explicit `PYTHONPATH`, and a timeout. It records exit status, duration, and
bounded stdout/stderr in `TestRunResult`.

This is a command-construction safety boundary, not a general sandbox. A future
patch-writing agent could make source code unsafe to import, so the production
version must run case workspaces in a separate container or equivalent OS-level
isolation. Until then, this runner is permitted only for self-owned EventRelay
fixtures on D drive.
