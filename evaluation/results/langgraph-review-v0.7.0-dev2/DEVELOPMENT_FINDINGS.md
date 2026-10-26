# Development result status

This directory preserves the first complete `0.7.0-dev2` development run exactly as recorded:
`3/5 pass@1`, two safe handoffs, and zero incorrect accepted patches.

After completion, a repeated preflight exposed that the upstream HTTPie target
`tests/test_regressions.py::test_Host_header_overwrite` resolves and contacts `httpbin.org`. The fixed
commit can therefore fail when DNS, routing, the remote service, or its response changes. This makes
the benchmark environment non-deterministic even though the recorded attempt itself completed.

The ledger and report are retained and must not be rewritten. They are not used as the final
comparison result. The replacement benchmark is `langgraph-review-offline-v0.7.0-dev2`, which uses a
new repository fixture hash, task-config hash, manifest hash, and a local `HTTPRequest` oracle with no
network access.
