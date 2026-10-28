# TraceRepair Agent v0.8.0

Agent `0.8.0` combines LangGraph orchestration with native Function Calling,
a SHA-256 Prompt Registry, and read-only hybrid Code RAG. SQLite remains the
only durable state and checkpoint source. The model proposes tools and diffs;
the deterministic controller owns permissions, writes, tests, budgets, and
the final human-review boundary.

## Frozen locked result

Three previously unused repositories were preregistered at commit `45393f4`
and run once each:

- `jaraco.text`: target and regression passed
- `python-sortedcontainers`: target and regression passed
- `structlog`: safe handoff because the confirmed source slice did not include
  the failing method

Result: **2/3 pass@1, 1 safe handoff, 0 incorrect accepted patches**. Average
completion tokens were `414.33`; P50/P95 wall time was `13.047s` / `21.157s`.
The Wilson 95% interval is `[0.2077, 0.9385]`, which makes the small-sample
claim boundary explicit.

Every result, including the failure, is retained in a SHA-256 hash-chained
ledger. This release does not claim a general 66.67% repair rate.
