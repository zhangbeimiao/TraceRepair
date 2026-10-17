# Milestone 2.5: deterministic diagnostic workflow

This controller is an integration harness for the first safe tool path:

```text
ready -> running -> repo_map -> search_code -> read_file -> run_tests -> needs_human
```

Tool completion is read from the SQLite checkpoint, so a process restart resumes
at the first unfinished step rather than repeating a repository map or test run.
The workflow never writes a patch. It deliberately hands off after the target
test because a future planner must supply evidence-backed repair decisions.
