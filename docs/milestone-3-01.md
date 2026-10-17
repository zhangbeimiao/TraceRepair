# Milestone 3.01: generalize the frozen single-case agent

## Baseline

Case 05 was frozen for agent `0.3.0` after five same-version attempts: four
passed the target and regression suites and one stopped safely on
`PATCH_CONTEXT_MISMATCH`. The frozen manifest preserves all five outcomes.

## Generalized development set

Agent `0.4.0-dev1` accepts development cases 01, 03, 05, 07, and 10. The live
runner reads only the public issue from the case catalog. It does not send the
catalogued faulty path, injected replacement, or reference repair to the model.

Diagnosis receives the failing target name and one public entrypoint hint:

- case 01: `def seen`;
- case 03: `def retry`;
- case 05: `def read_bool`;
- case 07: `def list_after`;
- case 10: `def handle_batch`.

These hints identify public behavior, not the faulty condition or replacement.
If model-driven search exhausts its budget, deterministic recovery may search
the hint and read a file only when every bounded hit resolves to one allowlisted
path. Patch policy and both verification gates remain unchanged.

## Verification

- every development snapshot was materialized successfully;
- every snapshot failed its own target test before repair;
- 23 target-runner, materialization, catalog, and generalized workflow tests passed;
- the frozen `0.3.0` cohort remains separate from `0.4.0-dev1` traces.

The next step is one live attempt per new development case, starting with case
01 so failures can be diagnosed independently rather than hidden inside a batch.
