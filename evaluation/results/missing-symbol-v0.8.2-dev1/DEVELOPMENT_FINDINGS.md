# Missing-symbol diagnosis 0.8.2-dev1: development findings

Three previously observed cases were each attempted once. This is development
data and does not establish a general repair rate or causal effect.

| Case | Outcome | Model calls | Completion tokens | Wall seconds |
| --- | --- | ---: | ---: | ---: |
| structlog-missing-event | review handoff, draft not applied | 4 | 332 | 9.313 |
| tqdm-sizeless-bool | patch-generation handoff, no draft | 4 | 219 | 7.219 |
| httpie-host-header-offline | patch-generation handoff, no draft | 3 | 171 | 5.485 |

Summary: 0/3 pass@1; three human handoffs; zero incorrect patches accepted.
Average completion tokens: 240.67. None of the three candidates was accepted.
The previous 0.8.1-dev1 development cohort achieved 2/3 on the same cases;
one attempt per case cannot distinguish a regression caused by a specific
change from model variability.

## Structlog

The model read `src/structlog/dev.py` lines 93–200, then requested lines
195–260 and produced a draft. Its draft changed `event_dict.pop("event")` to
`event_dict.pop("event", "")`. The semantic reviewer handed off because it
did not see test assertions specifying the expected missing-event output. The
registered test is under `tests/`, outside the configured `src/structlog` read
allowlist; the new test-observation helper was also not triggered because no
diagnostic search returned zero hits. The draft was not applied or tested.

Draft artifact SHA-256:
`6d4245ed656469929f7d8bc097712beaf79d3d64bbe5a3d26e0b70ade0e6da1d`.
The original candidate is in the disposable local task workspace; the public
record here includes only the relevant changed line and its digest.

## Tqdm

The host observed the registered `test_bool` at lines 1711–1763 after the
first zero-hit search. The model nevertheless searched both `def __bool__`
and `__bool__`, both returning zero hits, then searched for `def __len__`.
At the third and final diagnosis turn, deterministic recovery read
`tqdm/_tqdm.py` lines 870–1069. The patch-stage model handed off because no
`__bool__` definition was visible. The buggy implementation indeed does not
define that method; an absent method may require an addition rather than
copying removed lines. The recorded patch prompt length reached the 9,000
character cap, so context truncation is a further possibility to inspect, not
a proven cause. The model made no candidate patch and tests did not run.

## HTTPie

The model initially read `httpie/models.py` lines 80–130, including the
relevant `HTTPRequest` code. It then requested lines 1–50 as a supplementary
read. The 0.8.1 source-refinement implementation replaces the original slice
with the second slice; therefore the next patch-generation prompt did not
include the earlier relevant code, and the model handed off. This is a concrete
context-retention defect, independent of whether the supplementary request was
itself useful. No candidate patch or tests ran.

## Integrity

- Report file SHA-256: `ffdbda9ff32bcde99ee7efad073d1f13fe3edf7c8d4119eb3360a4b9f218c11c`
- Terminal ledger SHA-256: `955241e8a4a0a1c4c3e7283396ab45ecc104c2020015cc6f0b27d35866b73e2c`
- Manifest SHA-256: `83aedc0e77408ed2cfd665f05bb89353ed5629681fb420f13c6881b5e7a29e06`

Hash chains provide tamper evidence once their terminal digest is published;
they are not immutable storage. Preserve this cohort and use a new agent
version and a new development report for any subsequent change.
