# Milestone 3.04: frozen release report and local Web showcase

The `0.4.0-dev1` evidence includes eight successful development runs across four bug types and
five successful one-shot locked runs across five previously untouched bug types. The combined
snapshot contains thirteen verified repairs across nine bug types. These figures describe the
controlled EventRelay benchmark, not arbitrary-repository performance.

`scripts/export_web_demo.py` joins the two immutable manifests with sanitized SQLite trace data.
It writes a machine-readable release summary and a dependency-free local Web dashboard under
`demo/dist`. The browser payload excludes source bodies, patches, raw model responses, test output,
workspace paths, environment variables, and credentials.

The dashboard explains the hybrid architecture, separates development and locked results, keeps
historical failures visible by version cohort, and lets an interviewer inspect the real state and
tool timeline for every frozen run.
