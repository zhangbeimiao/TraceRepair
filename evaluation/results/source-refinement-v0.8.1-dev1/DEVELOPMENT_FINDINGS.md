# Source refinement 0.8.1-dev1: development findings

This is a single pass over three previously observed development cases. The
structlog case previously appeared in the 0.8.0 locked cohort and is no longer
eligible as an unseen evaluation. These results do not establish a general repair
rate or a causal improvement from one stochastic run.

| Case | Outcome | Model calls | Completion tokens | Wall seconds |
| --- | --- | ---: | ---: | ---: |
| structlog-missing-event | target + regression passed; awaiting review | 4 | 482 | 12.844 |
| tqdm-sizeless-bool | needs human before a candidate patch | 4 | 217 | 6.500 |
| httpie-host-header-offline | target + regression passed; awaiting review | 3 | 547 | 16.563 |

Summary: 2/3 pass@1, one human handoff, no incorrect patch accepted, average
completion tokens 415.33. Every task was run once within this development
cohort. Success means the registered tests passed, with human review still
required; it does not prove semantic correctness beyond the tests.

## Structlog trace

The model first read `src/structlog/dev.py` lines 93–180. In the new
`patch_context` stage it requested the same file at lines 180–270, recorded as
`source_refined`. It then proposed a diff, the semantic reviewer revised it,
and the reviewed diff passed patch policy, the target test, and the configured
regression test. The draft SHA-256 is
`47719a6c406f010d2c0df82ff3e5a22656c377fd6d10e583b70b9e30739a50e6`;
the applied reviewed diff SHA-256 is
`e813bb8ae06bd254f9cb2356f4ffb4b6d2b2e9d47cd2a48d66fd7fec826ec9a3`.
This confirms that the new bounded read was exercised in this run; the single
run alone does not quantify the mechanism's causal effect.

## Tqdm trace

The model spent its three diagnosis turns searching `def __bool__`, `__bool__`,
and `test_bool`. The first two searches returned no hits. The deterministic
fallback eventually read `tqdm/_tqdm.py` lines 870–1069, including the existing
`__len__` method at line 950. Because the three-turn diagnosis budget was already
exhausted, the additional read was not advertised. The model then handed off,
stating that `__bool__` was not visible. In the buggy snapshot the source has
no `__bool__` definition, so looking for its existing definition is not a
sufficient debugging strategy. No patch was applied and no target test ran.

The two cases expose different problems: a bounded missing source slice for
structlog, and search strategy/budget plus an absent method for tqdm. Increasing
the read budget alone should not be presented as a proven fix for tqdm.

## Integrity

- Report file SHA-256: `6684bd4a8604b87d29bde69bea05d20115547ac0e213eb54aa1a26fe9afc960e`
- Terminal ledger SHA-256: `9081483967df8e28e07ab3eecc9d416eee07a8fa333673938e5e0be193de10e0`
- Manifest SHA-256: `fb6bc1b4a366b8733227ea39e049808edff7c4f6418939996f9f72ba9b77e031`

These hashes make changes detectable against a trusted published reference;
they do not make local files immutable.
