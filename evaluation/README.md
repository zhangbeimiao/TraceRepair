# Case workspaces

Each evaluation case is created by copying the reference implementation into a
disposable workspace and applying one transformation from `cases.json`.

The agent sees the Issue text and the faulty workspace. It never sees the
reference source, transformation definition, or evaluator-only checks.
