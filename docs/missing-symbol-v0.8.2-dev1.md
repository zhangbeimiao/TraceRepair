# Missing-symbol diagnosis: 0.8.2-dev1

In the known tqdm development task, searches for `def __bool__` and `__bool__`
returned no matches. The buggy snapshot has `__len__` but no `__bool__` in its
main implementation. The registered test describes explicit totals, normal
iterables, generators without a length and manual operation. A zero-hit search
is evidence about the bounded search, not proof that a method does not exist or
that a particular implementation is correct.

The new diagnosis prompt preserves up to three zero-hit queries and the public
diagnostic hints. It asks the planner to consider a missing, inherited or
differently named method and inspect related source and test behavior. Following
the first zero-hit search, the host may make one bounded observation of the
registered test function if its exact file is inside the existing read allowlist:
at most one search, one 80-line read and 3,500 evidence characters. The test is
untrusted evidence, wrapped by the prompt's existing delimiter escaping. Missing
or inaccessible tests do not grant extra access. Test files, including tests
nested under a source root, cannot be patched.

The model still has three diagnosis turns, five model calls and the existing
completion-token budget. The additional host-side search and read are separate
instrumented tool calls, not model calls. An observed test excerpt may contain
neighboring lines and can be truncated; it is not a complete oracle. All
normal patch, target-test, regression and human-review gates remain mandatory.

All three tasks in `missing-symbol-v0.8.2-dev1` are known development data,
including structlog's previously locked case. A passing result cannot be reported
as blind evidence. A later frozen locked evaluation requires new repositories.

The first live development run yielded 0/3 and three safe handoffs. Its full
trace analysis is retained in
`evaluation/results/missing-symbol-v0.8.2-dev1/DEVELOPMENT_FINDINGS.md`. The
HTTPie trace exposed replacement of the first source slice by the second;
structlog exposed missing registered-test evidence during review; tqdm still
repeated semantically equivalent zero-hit searches. These are distinct observed
failure modes, not a claim that the prompt change caused all three failures.
