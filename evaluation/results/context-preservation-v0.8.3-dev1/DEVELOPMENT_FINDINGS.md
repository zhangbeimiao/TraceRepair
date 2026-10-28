# Context preservation 0.8.3-dev1: development findings

Three previously observed development cases were attempted once each. This
cohort is not a locked evaluation and does not establish a general repair rate
or prove that the observed change in outcomes was caused by any one mechanism.

| Case | Outcome | Model calls | Completion tokens | Wall seconds |
| --- | --- | ---: | ---: | ---: |
| structlog-missing-event | target + configured regression passed; awaiting review | 4 | 503 | 14.781 |
| tqdm-sizeless-bool | handoff, combined source range exceeds 200 lines | 2 | 158 | 7.141 |
| httpie-host-header-offline | target + configured regression passed; awaiting review | 3 | 619 | 15.375 |

The result is 2/3 pass@1, one human handoff, zero incorrect accepted patches,
and 426.67 average completion tokens. Passing cases still require human review.
The configured regressions for structlog and HTTPie are registered test files,
not the complete upstream project suites; passing them is not proof of general
semantic correctness.

## Structlog

The model read `src/structlog/dev.py` lines 93–185, then requested 185–275.
The controller reread and verified the combined range 93–275, preserving both
observations; the patch-stage source was not truncated. The host read the
registered target test at `tests/test_tracerepair_missing_event.py` lines 6–15
for the reviewer, also without truncation. The reviewer returned the unchanged
draft, and the configured target and regression passed. This run shows the
combined read and registered-test observation were exercised; a single run
cannot establish their causal contribution to the outcome.

## Tqdm

The model initially read `tqdm/tests/tests_tqdm.py` lines 1700–1760. The
controller's source recovery then found and read `tqdm/_tqdm.py` lines
870–1069. At patch stage the model requested lines 1069–1200. The two source
ranges span lines 870–1200, or 331 lines, so the controller stopped safely
under the 200-line combined-range limit. The additional read itself completed,
but no combined checkpoint, candidate patch or target test was produced.

The first test-file slice was not stored as the graph's `test_observation`:
it was a model-selected test read followed immediately by deterministic source
recovery, not a zero-hit-triggered registered-test observation. This is a
separate context-retention limitation, not proof that the model would have
repaired the case if the range limit were relaxed.

## HTTPie

The model read `httpie/models.py` lines 80–130 and directly proposed a draft;
there was no supplementary source read in this run. The host read the registered
test, the reviewer revised the draft, and the target and configured regression
passed. This case therefore does not itself exercise the source-merge path;
the relevant disjoint-read behavior is covered by deterministic tests.

## Integrity and version boundaries

- Report file SHA-256: `cf5c6d4dacfeef3d2fad271b293b94324df4607bd61caf1e83bb788cbef7f600`
- Terminal ledger SHA-256: `463d249f97784038c9f702eb481caeb2ad50ba1f1c8da71e7b1a7e636f674c07`
- Manifest SHA-256: `44344f62de4a69c98e874111aad7825ba6c63b26de58ae0763f2e92d94e0aeac`

The earlier 0.8.1-dev1 2/3 and 0.8.2-dev1 0/3 development reports remain
separate. Their different single-run outcomes cannot be interpreted as a
statistically reliable comparison. Hashes provide tamper evidence against a
trusted published reference, not immutable storage.
