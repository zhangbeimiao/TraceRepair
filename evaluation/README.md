# Case workspaces

Each evaluation case is created by copying the reference implementation into a
disposable workspace and applying one transformation from `cases.json`.

The agent sees the Issue text and the faulty workspace. It never sees the
reference source, transformation definition, or evaluator-only checks.

# Frozen baseline replay

The baseline entrypoint verifies and normalizes existing evidence. It makes no
provider request and does not rerun a locked task:

```powershell
python -m evaluation.run --suite locked_v1 --agent-version 0.8.0
python -m evaluation.run --suite current_v1 --agent-version 0.8.5-dev1
python -m evaluation.run --suite portfolio_v1 --agent-version mixed-historical
python -m evaluation.report --run runs\locked_v1.json
```

`locked_v1` is the latest proper one-shot locked evidence (three independent
historical bugs, agent 0.8.0). `current_v1` freezes the current 0.8.5-dev1
development evidence and must not be described as locked. `portfolio_v1`
separates the legacy 13 EventRelay runs, five repeats of one public-repository
bug, and one held-out run: 19 observed runs cover 11 independent bugs and eight
repeats. The held-out task configuration is not published, so it is explicitly
evidence-only rather than reproducible from the public repository.

JSON and Markdown outputs retain every failure and `needs_human` result. Fields
not preserved by the source evidence (Diff, latency, cost, or test gates) remain
null or explicitly unavailable; they are never inferred from a success label.
