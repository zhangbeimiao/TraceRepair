# Milestone 2.2: read-only repository tools

The first tools are intentionally small and have no command execution path.

- `repo_map` lists allowlisted text files and top-level Python symbols.
- `search_code` performs bounded, case-insensitive literal search.
- `read_file` returns a bounded, line-addressable text slice.

All paths must be relative to the configured workspace and must begin with
`src/` or `docs/`. Tests are deliberately outside this allowlist: a future
agent may run a restricted test command, but must not read or modify hidden
evaluation tests. Every rejected request returns a code such as `PATH_DENIED`
or `LINE_LIMIT_EXCEEDED`, so the graph can make a safe stop or retry decision.
