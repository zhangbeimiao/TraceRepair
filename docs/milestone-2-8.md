# Milestone 2.8: candidate repair loop

`CandidateRepairWorkflow` receives one externally supplied unified diff. It
reactivates a paused `needs_human` task, validates and applies the candidate,
then runs exactly the case's target test.

```text
needs_human -> ready -> running -> apply_patch -> run_tests
                                              -> awaiting_review (pass)
                                              -> needs_human (reject/fail)
```

Target-test success is deliberately not final success: it only means the patch
is eligible for a later regression test and human review. No model is connected
to this workflow.
