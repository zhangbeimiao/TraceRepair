# Native Function Calling v0.8.0-dev1 development findings

This is a complete five-task development result, not locked evidence and not a
claim about general repair accuracy.

- Result: `0/5 pass@1`.
- Format-contract failures: `5/5`.
- Four failures rejected an overlong or non-string `reason` field.
- One failure rejected a provider-selected function name outside the canonical
  function registry.
- No locked task was selected and no failed candidate was accepted.
- The original report, complete hash-chained ledger, per-task logs, protocol
  comparison, and SHA-256 files are retained unchanged.

The diagnosis tools themselves worked: successful calls included `repo_map`,
`search_code`, and `read_file`. Two tasks reached a policy-valid candidate diff,
then stopped during the semantic review call. The result therefore isolates a
provider-protocol compatibility problem rather than a tool execution failure.

Any compatibility normalization or Prompt/Schema change must use a new Agent
version and a new benchmark ID. This `0/5` result must never be overwritten or
rerun under the same manifest.
