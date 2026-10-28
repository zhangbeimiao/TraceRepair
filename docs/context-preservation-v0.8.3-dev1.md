# Context preservation and review evidence: 0.8.3-dev1

This development revision responds to the frozen 0.8.2-dev1 development
failures. The HTTPie failure showed that a later read replaced an earlier,
relevant source slice. The structlog reviewer could not see the registered test.
For tqdm, a local reconstruction of the old patch evidence is about 9,940
characters against a 9,000-character limit. The logged prompt length was 9,000;
the `__len__` definition begins near offset 4,993, before the cut. This supports
that some evidence was clipped, but does not prove truncation caused the handoff.

After a model-requested extra read, the host reads the contiguous union of the
old and new slices, capped at 200 lines. It verifies that both slices match the
union and persists the combined slice in the existing SQLite-backed checkpoint.
Ranges whose union exceeds 200 lines, inconsistent reads, and inaccessible
files safely hand off. This is intentionally conservative; widely separated
regions are not yet supported as two independent checkpointed slices.

At review, only the registered target test function can be observed by a
host-controlled read. The read remains bounded to 80 lines, with up to 1,200
characters included as untrusted evidence; it does not execute the test or
extend model tool permissions. Existing patch and test gates remain unchanged.

Patch and review prompts use explicit character budgets for test and source
evidence. If the source is shortened, both its beginning and end are retained,
the omission is marked, and a `context_budget_applied` trace event records the
sizes. A draft that cannot fit alongside essential source causes a human
handoff rather than silent truncation. These are character budgets, not exact
token counts. A bounded excerpt can still omit relevant middle lines.

The development manifest reuses previously known cases for diagnosis only.
The earlier 0.8.1-dev1 2/3 and 0.8.2-dev1 0/3 reports remain unchanged; any
future locked evaluation must use separately frozen, previously unused cases.

The first live development run obtained 2/3 pass@1 with one safe handoff.
Structlog exercised both the combined source checkpoint and registered-test
review evidence. Tqdm requested two ranges spanning 331 lines and was stopped
at the 200-line combined-range limit. HTTPie passed without a supplementary
read. See `evaluation/results/context-preservation-v0.8.3-dev1/DEVELOPMENT_FINDINGS.md`
for the complete scope and failure analysis; one run per known case does not
prove a general improvement.
