# LangGraph migration development findings

Run date: 2026-10-26 (Asia/Shanghai)

This is a known-task architecture-regression run for Agent `0.7.0-dev1`, not a
fresh locked-set evaluation. All five tasks were labelled development before the
run. The immutable Agent `0.6.0 / historical-python-v1.1.3` evidence remains
separate.

## Result

- pass@1: **2/5 (40%)**
- successful repairs: more-itertools, HTTPie
- safe target-test rejections: Humanize, Boltons, tqdm
- incorrect accepted patches: **0**
- human handoffs: 3
- average completion tokens: 315.6
- P50 / P95 wall time: 9.985s / 16.094s
- terminal ledger SHA-256:
  `b1018b9070795a64344a278af8f569250a38ac36f01f892f406d37847caa1881`
- report SHA-256:
  `c6d8824d9efd6293ffc608ad0aa540b795a16ad01e874768f43da203f1bbb81d`

The report payload also carries its canonical content digest
`695e9156883fe162075e34c85cfd994b815efe9c4a9a02901ff9a159e10a8415`;
the value above is the SHA-256 of the serialized `report.json` file.

## Failure analysis

All three failed candidates passed structural patch policy, were written only to
disposable workspaces, then failed the registered target test. None reached the
regression gate or `awaiting_review`.

1. **Humanize**: the candidate made every negative numerator positive. That
   fixes negative mixed numbers but breaks negative proper fractions where the
   sign must remain on the numerator. The historical fix applies `abs()` only
   when formatting the mixed-fraction branch.
2. **Boltons**: the candidate compiled an empty regular expression and returned
   from the constructor. The later substitution still treats the empty pattern
   as a match. The historical fix makes `sub()` return the input text when the
   replacement map is empty.
3. **tqdm**: the candidate returned `not self.disable`, which is unrelated to the
   required boolean contract. The historical fix prioritises explicit `total`,
   rejects manual mode without an iterable or total, and otherwise delegates to
   the iterable's truth value.

These are model semantic errors, not graph-routing failures. Every trace reached
the expected graph nodes, the target gate rejected all three wrong behaviours,
and SQLite recorded the terminal states. The result should not be rerun or
relabelled. Any prompt, review-node, or patch-generation change requires Agent
`0.7.0-dev2` and a new benchmark ID.

The exact five candidate diffs are retained in `candidates/`; successes and
failures are preserved alike.
