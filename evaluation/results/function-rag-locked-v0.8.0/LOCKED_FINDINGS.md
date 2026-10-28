# TraceRepair 0.8.0 locked findings

The public preregistration commit was `45393f4`. It froze Agent `0.8.0`,
Qwen `qwen3.8-flash`, native Function Calling, Prompt hashes, hybrid Code RAG,
the three task identities, and the pass@1 protocol before any model request.

## Result

- `2/3` pass@1 (`66.67%`)
- `1/3` safe human handoff
- `0` incorrect accepted patches
- average completion tokens: `414.33`
- P50/P95 wall time: `13.047s` / `21.157s`
- each locked task ran exactly once; no retry or post-hoc policy change

`jaraco-text-headless-camel` and `sortedcontainers-empty-extend` passed both
their registered target tests and full regressions, then stopped at
`awaiting_review`. `structlog-missing-event` did not produce or apply a patch:
the model correctly reported that the retrieved source slice ended before
`ConsoleRenderer.__call__`, so an exact minimal edit could not be justified.
The controller preserved that outcome as `needs_human`.

This is evidence for a bounded, auditable workflow on three previously unused
repositories. It is not evidence of a universal 66.67% code-repair rate.
