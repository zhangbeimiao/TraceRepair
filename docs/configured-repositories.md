# Configured repository adapter

TraceRepair `v0.6.0` can repair a trusted small Python repository without adding
repository-specific Python code. A JSON task supplies the boundaries that used
to be hard-coded for EventRelay:

```json
{
  "$schema": "../../docs/repository-task.schema.json",
  "schema_version": 1,
  "name": "mini-repo-discount",
  "repository_root": "../mini_repo",
  "issue": "apply_discount returns the discount amount instead of the remaining price",
  "source_allowlist": ["src/minimath"],
  "target_test": "tests/test_pricing.py::test_apply_discount_returns_remaining_price",
  "regression_suite": "tests",
  "diagnostic_queries": ["def apply_discount"],
  "pythonpath": ["src"]
}
```

Run the bundled zero-cost proof:

```powershell
python scripts\generic_repository_demo.py
```

Run the same adapter with the configured Bailian model:

```powershell
python scripts\model_repair_agent.py --task examples\tasks\mini-repo.json
```

After the first real run, fill a five-run stability cohort without duplicating
already persisted runs:

```powershell
python scripts\benchmark_repository.py
```

The command starts at most four new runs, caps each run at four provider calls,
and freezes a manifest only when at least four of five attempts succeed.

The adapter resolves relative paths from the JSON file, validates repository
size and file count, rejects C: repositories on the Windows workstation, and
copies accepted files into a disposable workspace. The model sees only files
under `source_allowlist`; candidate patches may only modify Python files under
the same roots. Target and regression selectors are passed to `pytest` as
argument-list elements with `shell=False`; arbitrary pytest options are denied.

This boundary is not an OS sandbox. Pytest imports and executes repository code,
so the current adapter is for repositories the operator owns or otherwise
trusts. Running unknown third-party code requires a later container sandbox.

The complete machine-readable schema is `docs/repository-task.schema.json`.
