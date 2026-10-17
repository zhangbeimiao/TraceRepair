# EventRelay baseline architecture

EventRelay accepts a batch of webhook-like events. Each event contains an ID,
event type, UTC timestamp, and payload. The baseline has deliberately small,
separable modules so a repair agent must navigate and reason about a repository
rather than solve one monolithic function.

```text
validate input -> idempotency gate -> process event -> record success
                         |                  |
                         |                  +-> retry policy (for retryable errors)
                         +-> SQLite event store -> cursor pagination
```

## Invariants

1. Unknown top-level event fields are rejected.
2. An event is deduplicated only by its `event_id`.
3. Timestamps are normalised to UTC before comparisons.
4. `max_retries` means the number of retries after the initial attempt.
5. An event is marked processed only after its handler succeeds.
6. A single bad item in a batch must not prevent valid items from being handled.
7. Cursors are exclusive: a page never repeats its previous final item.

## Planned agent boundary

The later TraceRepair graph will receive an Issue and operate on a disposable
case workspace. It may use repository-map, search, read-file, retrieve-docs,
apply-patch, run-tests, and inspect-diff tools. It cannot edit tests or invoke
arbitrary commands.
