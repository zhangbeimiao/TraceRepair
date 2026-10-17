# Milestone 2.1: deterministic task records

This milestone deliberately excludes the agent graph and executable tools. It
defines the contracts that future components must share and persists only
JSON-safe task checkpoints and trace metadata in SQLite.

Large artifacts such as source files, raw test logs, and candidate diffs are not
embedded in a checkpoint. Later nodes will store their D-drive paths and hashes
in state instead. This keeps checkpoints small, prevents repeated context
expansion, and makes a resumed task auditable.

The next milestone will add read-only repository tools. No model is needed to
test those tools or the state transition policy.
