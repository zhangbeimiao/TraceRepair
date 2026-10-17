# Milestone 2.6: candidate patch policy

Before a future patch can touch a workspace, its unified diff must pass static
policy validation. The first policy permits only small modifications to existing
Python files under `src/eventrelay/`; it rejects tests, configuration, absolute
paths, path traversal, deletions, oversized diffs, and diffs without hunks.

This module deliberately has no file-write function. Keeping validation separate
from application makes policy behaviour straightforward to unit test and trace.
