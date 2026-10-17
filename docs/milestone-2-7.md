# Milestone 2.7: guarded patch application

`PatchApplier` only operates on a disposable case workspace. It validates a
unified diff with `PatchPolicy`, parses the diff without invoking a shell, checks
all hunk context in memory, and writes only after every target file validates.

The tool trace records the candidate diff hash, policy outcome, modified paths,
and final content hashes. It never stores the raw diff in SQLite. A rejected or
context-mismatched patch leaves the workspace unchanged.
