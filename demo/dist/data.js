window.TRACEREPAIR_DEMO = {
  "generatedAt": "2026-10-17T15:35:55.928263+00:00",
  "summary": {
    "agentVersion": "0.4.0-dev1",
    "evaluatedBugTypes": 9,
    "runs": 13,
    "successes": 13,
    "successRate": 1.0,
    "averageTokens": 224.38,
    "averageToolCalls": 5.0,
    "development": {
      "case_ids": [
        "01",
        "03",
        "07",
        "10"
      ],
      "agent_version": "0.4.0-dev1",
      "runs": 8,
      "successful_runs": 8,
      "success_rate": 1.0,
      "average_completion_tokens": 212.62,
      "average_tool_calls": 5.0,
      "stop_reasons": {},
      "minimum_runs_per_case": 2,
      "required_success_rate": 0.8,
      "required_case_success_rate": 0.5,
      "cases": [
        {
          "case_id": "01",
          "agent_version": "0.4.0-dev1",
          "runs": 2,
          "successful_runs": 2,
          "success_rate": 1.0,
          "average_completion_tokens": 262.0,
          "average_tool_calls": 5.0,
          "stop_reasons": {},
          "minimum_runs": 2,
          "required_success_rate": 0.5,
          "stable": true
        },
        {
          "case_id": "03",
          "agent_version": "0.4.0-dev1",
          "runs": 2,
          "successful_runs": 2,
          "success_rate": 1.0,
          "average_completion_tokens": 179.5,
          "average_tool_calls": 5.0,
          "stop_reasons": {},
          "minimum_runs": 2,
          "required_success_rate": 0.5,
          "stable": true
        },
        {
          "case_id": "07",
          "agent_version": "0.4.0-dev1",
          "runs": 2,
          "successful_runs": 2,
          "success_rate": 1.0,
          "average_completion_tokens": 233.0,
          "average_tool_calls": 5.0,
          "stop_reasons": {},
          "minimum_runs": 2,
          "required_success_rate": 0.5,
          "stable": true
        },
        {
          "case_id": "10",
          "agent_version": "0.4.0-dev1",
          "runs": 2,
          "successful_runs": 2,
          "success_rate": 1.0,
          "average_completion_tokens": 176.0,
          "average_tool_calls": 5.0,
          "stop_reasons": {},
          "minimum_runs": 2,
          "required_success_rate": 0.5,
          "stable": true
        }
      ],
      "stable": true
    },
    "locked": {
      "case_ids": [
        "02",
        "04",
        "06",
        "08",
        "09"
      ],
      "agent_version": "0.4.0-dev1",
      "runs": 5,
      "successful_runs": 5,
      "success_rate": 1.0,
      "average_model_calls": 3.0,
      "average_completion_tokens": 243.2,
      "average_tool_calls": 5.0,
      "stop_reasons": {},
      "run_counts": {
        "02": 1,
        "04": 1,
        "06": 1,
        "08": 1,
        "09": 1
      },
      "complete": true
    }
  },
  "cohorts": [
    {
      "version": "0.3.0",
      "runs": 5,
      "successes": 4,
      "successRate": 0.8,
      "averageTokens": 253.2
    },
    {
      "version": "0.4.0-dev1",
      "runs": 13,
      "successes": 13,
      "successRate": 1.0,
      "averageTokens": 224.38
    },
    {
      "version": "legacy",
      "runs": 7,
      "successes": 3,
      "successRate": 0.4286,
      "averageTokens": 206.14
    }
  ],
  "traces": [
    {
      "taskId": "model-agent-01-1b58a202",
      "caseId": "01",
      "caseName": "idempotency-key",
      "split": "development",
      "issue": "Different event IDs with identical payload are incorrectly treated as duplicates.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 263,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=57; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=2; paths=['src/eventrelay/idempotency.py', 'src/eventrelay/processor.py']",
        "model -> read_file; tokens=39; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/idempotency.py",
        "phase -> patch_generation",
        "model -> patch; tokens=167; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/idempotency.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=438",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=452",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/idempotency.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/idempotency.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/idempotency.py"
          },
          {
            "kind": "meta",
            "text": "@@ -6,7 +6,7 @@"
          },
          {
            "kind": "context",
            "text": "         self._processed: set[str] = set()"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     def seen(self, event: Event) -> bool:"
          },
          {
            "kind": "removed",
            "text": "-        return str(sorted(event.payload.items())) in self._processed"
          },
          {
            "kind": "added",
            "text": "+        return event.event_id in self._processed"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     def mark_processed(self, event: Event) -> None:"
          },
          {
            "kind": "removed",
            "text": "-        self._processed.add(str(sorted(event.payload.items())))"
          },
          {
            "kind": "added",
            "text": "+        self._processed.add(event.event_id)"
          }
        ],
        "addedLines": 2,
        "removedLines": 2,
        "diffSha256": "13eec1ede7a6d0a2330c89bebbd207fd19fcdcf88d1eeae6a39564e025880d48",
        "contentSha256": "778ce0ab6bd93a9b54e4e7259d04b5b2174f49d5515f56b86f81036b7a9e2cc4",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 438,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 452,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-01-e5c699d8",
      "caseId": "01",
      "caseName": "idempotency-key",
      "split": "development",
      "issue": "Different event IDs with identical payload are incorrectly treated as duplicates.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 261,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=56; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=2; paths=['src/eventrelay/idempotency.py', 'src/eventrelay/processor.py']",
        "model -> read_file; tokens=38; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/idempotency.py",
        "phase -> patch_generation",
        "model -> patch; tokens=167; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/idempotency.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=421",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=422",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/idempotency.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/idempotency.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/idempotency.py"
          },
          {
            "kind": "meta",
            "text": "@@ -6,7 +6,7 @@"
          },
          {
            "kind": "context",
            "text": "         self._processed: set[str] = set()"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     def seen(self, event: Event) -> bool:"
          },
          {
            "kind": "removed",
            "text": "-        return str(sorted(event.payload.items())) in self._processed"
          },
          {
            "kind": "added",
            "text": "+        return event.event_id in self._processed"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     def mark_processed(self, event: Event) -> None:"
          },
          {
            "kind": "removed",
            "text": "-        self._processed.add(str(sorted(event.payload.items())))"
          },
          {
            "kind": "added",
            "text": "+        self._processed.add(event.event_id)"
          }
        ],
        "addedLines": 2,
        "removedLines": 2,
        "diffSha256": "13eec1ede7a6d0a2330c89bebbd207fd19fcdcf88d1eeae6a39564e025880d48",
        "contentSha256": "778ce0ab6bd93a9b54e4e7259d04b5b2174f49d5515f56b86f81036b7a9e2cc4",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 421,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 422,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-02-b28a23cd",
      "caseId": "02",
      "caseName": "timezone-normalisation",
      "split": "locked",
      "issue": "Legacy timestamps without a timezone crash later UTC comparisons.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 263,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=33; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/processor.py', 'src/eventrelay/validator.py']",
        "model -> read_file; tokens=34; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/validator.py",
        "phase -> patch_generation",
        "model -> patch; tokens=196; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/validator.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=422",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=452",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/validator.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/validator.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/validator.py"
          },
          {
            "kind": "meta",
            "text": "@@ -18,7 +18,7 @@"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     occurred_at = datetime.fromisoformat(raw[\"occurred_at\"].replace(\"Z\", \"+00:00\"))"
          },
          {
            "kind": "context",
            "text": "     if occurred_at.tzinfo is None:"
          },
          {
            "kind": "removed",
            "text": "-        occurred_at = occurred_at.replace(tzinfo=None)"
          },
          {
            "kind": "added",
            "text": "+        occurred_at = occurred_at.replace(tzinfo=UTC)"
          },
          {
            "kind": "context",
            "text": "     else:"
          },
          {
            "kind": "context",
            "text": "         occurred_at = occurred_at.astimezone(UTC)"
          },
          {
            "kind": "context",
            "text": "     return Event(raw[\"event_id\"], raw[\"event_type\"], occurred_at, raw[\"payload\"])"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "7a1f113320e36a73de8f4b8531cc7aafa6cf37ee3dd14c7875284679877ac1b7",
        "contentSha256": "4701a8ee29ab74fbca81c333f9dd4becef6b8687f05faf16f54fab72caa1a359",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 422,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 452,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-03-635d6fbd",
      "caseId": "03",
      "caseName": "retry-boundary",
      "split": "development",
      "issue": "max_retries is exceeded by one operation attempt.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 186,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=38; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=2; paths=['src/eventrelay/retry.py']",
        "model -> read_file; tokens=39; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/retry.py",
        "phase -> patch_generation",
        "model -> patch; tokens=109; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/retry.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=688",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=719",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/retry.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "@@ -18,6 +18,6 @@"
          },
          {
            "kind": "context",
            "text": "         try:"
          },
          {
            "kind": "context",
            "text": "             return operation()"
          },
          {
            "kind": "context",
            "text": "         except RetryableError:"
          },
          {
            "kind": "removed",
            "text": "-            if attempt > max_retries:"
          },
          {
            "kind": "added",
            "text": "+            if attempt >= max_retries:"
          },
          {
            "kind": "context",
            "text": "                 raise"
          },
          {
            "kind": "context",
            "text": "             attempt += 1"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "adecf3da287b1f1205b7f0347b5916dab341d975898dbabc54c30f9d42ebc400",
        "contentSha256": "669d29da7439232ec972274d12daaa5312e4788f3fd370174d3723953168856c",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 688,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 719,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-03-7dea02fd",
      "caseId": "03",
      "caseName": "retry-boundary",
      "split": "development",
      "issue": "max_retries is exceeded by one operation attempt.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 173,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=36; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=2; paths=['src/eventrelay/retry.py']",
        "model -> read_file; tokens=39; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/retry.py",
        "phase -> patch_generation",
        "model -> patch; tokens=98; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/retry.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=438",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=421",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/retry.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "@@ -18,6 +18,6 @@"
          },
          {
            "kind": "context",
            "text": "         try:"
          },
          {
            "kind": "context",
            "text": "             return operation()"
          },
          {
            "kind": "context",
            "text": "         except RetryableError:"
          },
          {
            "kind": "removed",
            "text": "-            if attempt > max_retries:"
          },
          {
            "kind": "added",
            "text": "+            if attempt >= max_retries:"
          },
          {
            "kind": "context",
            "text": "                 raise"
          },
          {
            "kind": "context",
            "text": "             attempt += 1"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "e17ce5703d7b4a325acc3fa215b5845df15b5f713893b373d119e1dded8ec8b5",
        "contentSha256": "669d29da7439232ec972274d12daaa5312e4788f3fd370174d3723953168856c",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 438,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 421,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-04-f19337b2",
      "caseId": "04",
      "caseName": "rate-limit-classification",
      "split": "locked",
      "issue": "HTTP 429 responses are discarded instead of retried.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 207,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=35; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/retry.py']",
        "model -> read_file; tokens=42; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/retry.py",
        "phase -> patch_generation",
        "model -> patch; tokens=130; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/retry.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=640",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=422",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/retry.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/retry.py"
          },
          {
            "kind": "meta",
            "text": "@@ -9,7 +9,7 @@"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": " def is_retryable_status(status_code: int) -> bool:"
          },
          {
            "kind": "removed",
            "text": "-    return status_code >= 500"
          },
          {
            "kind": "added",
            "text": "+    return status_code == 429 or status_code >= 500"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": " def retry(operation: Callable[[], T], max_retries: int) -> T:"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "2e0377cf1b846719d6c6900e0ef569ce1ebc23cc3a1f2b79a87e6be0ce2aedf2",
        "contentSha256": "669d29da7439232ec972274d12daaa5312e4788f3fd370174d3723953168856c",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 640,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 422,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-06-f84f3601",
      "caseId": "06",
      "caseName": "strict-schema",
      "split": "locked",
      "issue": "Unsupported top-level event fields are silently accepted.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 217,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=36; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/processor.py', 'src/eventrelay/validator.py']",
        "model -> read_file; tokens=36; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/validator.py",
        "phase -> patch_generation",
        "model -> patch; tokens=145; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/validator.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=391",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=436",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/validator.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/validator.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/validator.py"
          },
          {
            "kind": "meta",
            "text": "@@ -9,7 +9,7 @@"
          },
          {
            "kind": "context",
            "text": " def parse_event(raw: dict[str, Any]) -> Event:"
          },
          {
            "kind": "context",
            "text": "     unknown = set(raw) - _REQUIRED"
          },
          {
            "kind": "context",
            "text": "     missing = _REQUIRED - set(raw)"
          },
          {
            "kind": "removed",
            "text": "-    if False:"
          },
          {
            "kind": "added",
            "text": "+    if unknown:"
          },
          {
            "kind": "context",
            "text": "         raise ValueError(f\"unknown fields: {sorted(unknown)}\")"
          },
          {
            "kind": "context",
            "text": "     if missing:"
          },
          {
            "kind": "context",
            "text": "         raise ValueError(f\"missing fields: {sorted(missing)}\")"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "9b7ae5928c9cf9107447e071d2c8ebd499089a9a7a76d03bbec03b281020d71a",
        "contentSha256": "4701a8ee29ab74fbca81c333f9dd4becef6b8687f05faf16f54fab72caa1a359",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 391,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 436,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-07-4efb4ecf",
      "caseId": "07",
      "caseName": "cursor-boundary",
      "split": "development",
      "issue": "Page two repeats the final event from page one.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 219,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=35; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/storage.py']",
        "model -> read_file; tokens=36; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/storage.py",
        "phase -> patch_generation",
        "model -> patch; tokens=148; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/storage.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=750",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=578",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/storage.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/storage.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/storage.py"
          },
          {
            "kind": "meta",
            "text": "@@ -15,4 +15,4 @@"
          },
          {
            "kind": "context",
            "text": "         if cursor is None:"
          },
          {
            "kind": "context",
            "text": "             return ordered[:limit]"
          },
          {
            "kind": "context",
            "text": "         cursor_time = datetime.fromisoformat(cursor.replace(\"Z\", \"+00:00\")).astimezone(UTC)"
          },
          {
            "kind": "removed",
            "text": "-        return [item for item in ordered if item.occurred_at >= cursor_time][:limit]"
          },
          {
            "kind": "added",
            "text": "+        return [item for item in ordered if item.occurred_at > cursor_time][:limit]"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "eb40ad77d8b8d5970f9fd8540f14e10a2756e784f9c6e60ea39c294ba259cf6d",
        "contentSha256": "ae1ca21e4b00226bb10b52c8d773e72bf4501a5fd58080b0752dca614d40200f",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 750,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 578,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-07-9bcfd24d",
      "caseId": "07",
      "caseName": "cursor-boundary",
      "split": "development",
      "issue": "Page two repeats the final event from page one.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 247,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=40; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/storage.py']",
        "model -> read_file; tokens=34; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/storage.py",
        "phase -> patch_generation",
        "model -> patch; tokens=173; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/storage.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=422",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=438",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/storage.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/storage.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/storage.py"
          },
          {
            "kind": "meta",
            "text": "@@ -15,4 +15,4 @@"
          },
          {
            "kind": "context",
            "text": "         if cursor is None:"
          },
          {
            "kind": "context",
            "text": "             return ordered[:limit]"
          },
          {
            "kind": "context",
            "text": "         cursor_time = datetime.fromisoformat(cursor.replace(\"Z\", \"+00:00\")).astimezone(UTC)"
          },
          {
            "kind": "removed",
            "text": "-        return [item for item in ordered if item.occurred_at >= cursor_time][:limit]"
          },
          {
            "kind": "added",
            "text": "+        return [item for item in ordered if item.occurred_at > cursor_time][:limit]"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "e9df0132551dd8d26a610a17c4fbc7adb48d6a4267be3f6b42ec911bb7bb4b0b",
        "contentSha256": "ae1ca21e4b00226bb10b52c8d773e72bf4501a5fd58080b0752dca614d40200f",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 422,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 438,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-08-721fbf1b",
      "caseId": "08",
      "caseName": "processing-order",
      "split": "locked",
      "issue": "A failed delivery is still recorded as already processed.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 309,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=33; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=6; paths=['src/eventrelay/processor.py']",
        "model -> read_file; tokens=52; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/processor.py",
        "phase -> patch_generation",
        "model -> patch; tokens=224; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/processor.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=686",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=563",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/processor.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "@@ -17,9 +17,12 @@"
          },
          {
            "kind": "context",
            "text": "         event = parse_event(raw)"
          },
          {
            "kind": "context",
            "text": "         if self.idempotency.seen(event):"
          },
          {
            "kind": "context",
            "text": "             return EventResult(event.event_id, \"duplicate\")"
          },
          {
            "kind": "removed",
            "text": "-        self.idempotency.mark_processed(event)"
          },
          {
            "kind": "removed",
            "text": "-        self._handler(event)"
          },
          {
            "kind": "removed",
            "text": "-        self.store.add(event)"
          },
          {
            "kind": "added",
            "text": "+        try:"
          },
          {
            "kind": "added",
            "text": "+            self._handler(event)"
          },
          {
            "kind": "added",
            "text": "+            self.store.add(event)"
          },
          {
            "kind": "added",
            "text": "+            self.idempotency.mark_processed(event)"
          },
          {
            "kind": "added",
            "text": "+        except Exception:"
          },
          {
            "kind": "added",
            "text": "+            raise"
          },
          {
            "kind": "context",
            "text": "         return EventResult(event.event_id, \"processed\")"
          },
          {
            "kind": "context",
            "text": " "
          },
          {
            "kind": "context",
            "text": "     def handle_batch(self, items: list[dict[str, Any]]) -> list[EventResult]:"
          }
        ],
        "addedLines": 6,
        "removedLines": 3,
        "diffSha256": "5e3816a37d13eb53aa70ee7dc52e6810a7c68e11743335cf95d8a6783bbc70b0",
        "contentSha256": "1a4dd65a313363870e226dc574195c37f5e7e8dc58bd1e49dcfc64eabdec9f65",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 686,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 563,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-09-5da70a9a",
      "caseId": "09",
      "caseName": "expiry-units",
      "split": "locked",
      "issue": "Retention compares milliseconds with seconds, preserving expired retry records.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 220,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=33; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/retention.py']",
        "model -> read_file; tokens=42; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/retention.py",
        "phase -> patch_generation",
        "model -> patch; tokens=145; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/retention.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=407",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=453",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/retention.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/retention.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/retention.py"
          },
          {
            "kind": "meta",
            "text": "@@ -11,4 +11,4 @@"
          },
          {
            "kind": "context",
            "text": "     records: list[RetryRecord], now_ms: int, retention_ms: int"
          },
          {
            "kind": "context",
            "text": " ) -> list[str]:"
          },
          {
            "kind": "context",
            "text": "     cutoff_ms = now_ms - retention_ms"
          },
          {
            "kind": "removed",
            "text": "-    return [record.event_id for record in records if record.recorded_at_ms < cutoff_seconds]"
          },
          {
            "kind": "added",
            "text": "+    return [record.event_id for record in records if record.recorded_at_ms < cutoff_ms]"
          }
        ],
        "addedLines": 1,
        "removedLines": 1,
        "diffSha256": "f6a7a22ec8fd662b249dc98de4ae26a96fb950b6064487696ceae4c9987a0485",
        "contentSha256": "2c963d942af7185854f2019441bb62881f498c3d20b7eea6e0eaf74ea53e9f0c",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 407,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 453,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-10-039cd3b9",
      "caseId": "10",
      "caseName": "batch-isolation",
      "split": "development",
      "issue": "One malformed event prevents later valid events in a batch from being processed.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 176,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=33; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/processor.py']",
        "model -> read_file; tokens=37; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/processor.py",
        "phase -> patch_generation",
        "model -> patch; tokens=106; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/processor.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=532",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=469",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/processor.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "@@ -30,5 +30,4 @@"
          },
          {
            "kind": "context",
            "text": "             except ValueError as error:"
          },
          {
            "kind": "context",
            "text": "                 event_id = str(item.get(\"event_id\", \"unknown\"))"
          },
          {
            "kind": "context",
            "text": "                 results.append(EventResult(event_id, \"rejected\", str(error)))"
          },
          {
            "kind": "removed",
            "text": "-                break"
          },
          {
            "kind": "context",
            "text": "         return results"
          }
        ],
        "addedLines": 0,
        "removedLines": 1,
        "diffSha256": "34f5c3cf9a5be39c2a99e942803e4cdee37ae88598f07f04f7841202ce9f8377",
        "contentSha256": "a9d786e96093eda18af54e5d7b594e64454f607a0b5ededa628f3600111680a2",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 532,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 469,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    },
    {
      "taskId": "model-agent-10-d9f35820",
      "caseId": "10",
      "caseName": "batch-isolation",
      "split": "development",
      "issue": "One malformed event prevents later valid events in a batch from being processed.",
      "status": "awaiting_review",
      "success": true,
      "modelCalls": 3,
      "tokens": 176,
      "toolCalls": 5,
      "toolFailures": 0,
      "recoveries": 0,
      "targetPassed": true,
      "regressionPassed": true,
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=33; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=1; paths=['src/eventrelay/processor.py']",
        "model -> read_file; tokens=37; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/processor.py",
        "phase -> patch_generation",
        "model -> patch; tokens=106; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=True; files=['src/eventrelay/processor.py']",
        "tool run_tests -> ok=True; exit_code=0; duration_ms=438",
        "tool run_regression -> ok=True; exit_code=0; duration_ms=421",
        "state running -> awaiting_review; reason=candidate patch passed target and regression tests; human review required"
      ],
      "patchPreview": {
        "file": "src/eventrelay/processor.py",
        "lines": [
          {
            "kind": "meta",
            "text": "--- a/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "+++ b/src/eventrelay/processor.py"
          },
          {
            "kind": "meta",
            "text": "@@ -30,5 +30,4 @@"
          },
          {
            "kind": "context",
            "text": "             except ValueError as error:"
          },
          {
            "kind": "context",
            "text": "                 event_id = str(item.get(\"event_id\", \"unknown\"))"
          },
          {
            "kind": "context",
            "text": "                 results.append(EventResult(event_id, \"rejected\", str(error)))"
          },
          {
            "kind": "removed",
            "text": "-                break"
          },
          {
            "kind": "context",
            "text": "         return results"
          }
        ],
        "addedLines": 0,
        "removedLines": 1,
        "diffSha256": "34f5c3cf9a5be39c2a99e942803e4cdee37ae88598f07f04f7841202ce9f8377",
        "contentSha256": "a9d786e96093eda18af54e5d7b594e64454f607a0b5ededa628f3600111680a2",
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace"
      },
      "verification": {
        "policy": {
          "ok": true,
          "detail": "model patch accepted as a candidate; deterministic policy still applies"
        },
        "apply": {
          "ok": true,
          "detail": "candidate written to disposable copy",
          "durationMs": null,
          "errorCode": null
        },
        "target": {
          "ok": true,
          "detail": "registered target test passed",
          "durationMs": 438,
          "errorCode": null
        },
        "regression": {
          "ok": true,
          "detail": "complete EventRelay regression passed",
          "durationMs": 421,
          "errorCode": null
        },
        "finalReason": "candidate patch passed target and regression tests; human review required"
      }
    }
  ],
  "failures": [
    {
      "taskId": "model-agent-0768469e",
      "caseId": "05",
      "caseName": "boolean-config",
      "title": "补丁上下文不匹配",
      "category": "patch_context_mismatch",
      "issue": "EventRelay config value 'false' must parse as False",
      "status": "needs_human",
      "agentVersion": "0.3.0",
      "modelCalls": 4,
      "tokens": 256,
      "toolCalls": 6,
      "control": {
        "stopReason": "candidate patch rejected: PATCH_CONTEXT_MISMATCH",
        "policyRejected": false,
        "deterministicRecoveries": 1,
        "patchAttempted": true,
        "patchApplied": false,
        "errorCode": "PATCH_CONTEXT_MISMATCH",
        "testsStarted": false
      },
      "controlOutcome": "受限补丁应用器在写入前验证上下文，拒绝候选补丁；目标测试和回归测试均未启动。",
      "lesson": "模型给出的 Diff 只能作为候选输入，必须由确定性上下文校验决定能否落盘。",
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=32; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=10; paths=['src/eventrelay/__init__.py', 'src/eventrelay/idempotency.py', 'src/eventrelay/processor.py', 'src/eventrelay/storage.py', 'src/eventrelay/validator.py']",
        "model -> search_code; tokens=38; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/processor.py', 'src/eventrelay/validator.py']",
        "model -> read_file; tokens=36; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/validator.py",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/config.py']",
        "tool read_file -> ok=True; path=src/eventrelay/config.py",
        "controller -> deterministic recovery",
        "phase -> patch_generation",
        "model -> patch; tokens=150; policy_accepted=True",
        "state running -> needs_human; reason=model candidate requires controlled verification",
        "state needs_human -> ready; reason=operator supplied candidate diff",
        "state ready -> running; reason=candidate repair started",
        "tool apply_patch -> ok=False; files=[]",
        "state running -> needs_human; reason=candidate patch rejected: PATCH_CONTEXT_MISMATCH"
      ]
    },
    {
      "taskId": "model-agent-8360ffff",
      "caseId": "05",
      "caseName": "boolean-config",
      "title": "诊断预算耗尽",
      "category": "diagnosis_budget_exhausted",
      "issue": "EventRelay config value 'false' must parse as False",
      "status": "needs_human",
      "agentVersion": "legacy",
      "modelCalls": 3,
      "tokens": 102,
      "toolCalls": 4,
      "control": {
        "stopReason": "diagnosis budget ended before a source file was read",
        "policyRejected": false,
        "deterministicRecoveries": 0,
        "patchAttempted": false,
        "patchApplied": false,
        "errorCode": null,
        "testsStarted": false
      },
      "controlOutcome": "控制器发现诊断轮次已经用完且证据不足，因此没有请求补丁、没有写文件，并安全转入人工处理。",
      "lesson": "预算不仅控制成本，也阻止 Agent 在证据不足时继续猜测。",
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=31; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=10; paths=['src/eventrelay/__init__.py', 'src/eventrelay/idempotency.py', 'src/eventrelay/processor.py', 'src/eventrelay/storage.py', 'src/eventrelay/validator.py']",
        "model -> search_code; tokens=34; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/processor.py', 'src/eventrelay/validator.py']",
        "model -> read_file; tokens=37; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/validator.py",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/config.py']",
        "state running -> needs_human; reason=diagnosis budget ended before a source file was read"
      ]
    },
    {
      "taskId": "model-agent-aab74d1d",
      "caseId": "05",
      "caseName": "boolean-config",
      "title": "非法补丁输出",
      "category": "invalid_patch_output",
      "issue": "EventRelay config value 'false' must parse as False",
      "status": "needs_human",
      "agentVersion": "legacy",
      "modelCalls": 4,
      "tokens": 274,
      "toolCalls": 5,
      "control": {
        "stopReason": "planner stopped safely: model proposed an invalid patch",
        "policyRejected": true,
        "deterministicRecoveries": 1,
        "patchAttempted": false,
        "patchApplied": false,
        "errorCode": null,
        "testsStarted": false
      },
      "controlOutcome": "模型输出没有通过结构与策略校验，控制器没有调用 apply_patch，工作副本保持不变。",
      "lesson": "结构化输出仍是不可信输入；解析失败和策略拒绝必须走可观察的安全停止路径。",
      "timeline": [
        "state new -> ready; reason=end-to-end workspace created",
        "state ready -> running; reason=end-to-end model workflow started",
        "phase -> diagnosis",
        "model -> search_code; tokens=36; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=10; paths=['src/eventrelay/__init__.py', 'src/eventrelay/idempotency.py', 'src/eventrelay/processor.py', 'src/eventrelay/storage.py', 'src/eventrelay/validator.py']",
        "model -> search_code; tokens=34; policy_accepted=True",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/processor.py', 'src/eventrelay/validator.py']",
        "model -> read_file; tokens=33; policy_accepted=True",
        "tool read_file -> ok=True; path=src/eventrelay/validator.py",
        "tool search_code -> ok=True; hit_count=3; paths=['src/eventrelay/config.py']",
        "tool read_file -> ok=True; path=src/eventrelay/config.py",
        "controller -> deterministic recovery",
        "phase -> patch_generation",
        "model -> invalid; tokens=171; policy_accepted=False",
        "state running -> needs_human; reason=planner stopped safely: model proposed an invalid patch"
      ]
    }
  ],
  "recoveryScenarios": [
    {
      "task_id": "recovery-demo-66022b98",
      "title": "读取源码后进程中断",
      "crash_point": "source_read",
      "phase_one_tools": [
        "search_code",
        "read_file"
      ],
      "phase_one_model_calls": 2,
      "resume_model_calls": 1,
      "skipped_tools": [
        "search_code",
        "read_file"
      ],
      "final_tools": [
        "search_code",
        "read_file",
        "apply_patch",
        "run_tests",
        "run_regression"
      ],
      "final_status": "awaiting_review",
      "integrity_guard": "源码恢复工件和当前工作副本同时通过 SHA-256 校验后，才允许继续生成补丁。",
      "timeline": [
        {
          "state": "done",
          "label": "DIAGNOSE",
          "detail": "search_code 与 read_file 成功，源码切片写入工作副本恢复工件。"
        },
        {
          "state": "checkpoint",
          "label": "CHECKPOINT",
          "detail": "SQLite 记录 source_read 阶段、相对工件路径和内容哈希。"
        },
        {
          "state": "crash",
          "label": "PROCESS EXIT",
          "detail": "故障注入将任务置为 interrupted，运行时对象全部丢失。"
        },
        {
          "state": "resume",
          "label": "RESTART",
          "detail": "重新打开 SQLite、重建工具与规划器，并校验源码恢复工件。"
        },
        {
          "state": "skip",
          "label": "SKIP COMPLETED",
          "detail": "search_code 和 read_file 不再执行，只进行剩余一次补丁模型调用。"
        },
        {
          "state": "pass",
          "label": "VERIFY",
          "detail": "补丁、目标测试和完整回归通过，进入 awaiting_review。"
        }
      ]
    },
    {
      "task_id": "recovery-demo-59c9df97",
      "title": "补丁落盘后进程中断",
      "crash_point": "patch_applied",
      "phase_one_tools": [
        "search_code",
        "read_file",
        "apply_patch"
      ],
      "phase_one_model_calls": 3,
      "resume_model_calls": 0,
      "skipped_tools": [
        "apply_patch"
      ],
      "final_tools": [
        "search_code",
        "read_file",
        "apply_patch",
        "run_tests",
        "run_regression"
      ],
      "final_status": "awaiting_review",
      "integrity_guard": "恢复时重新计算已修改文件哈希；若内容变化，目标测试不会启动并转入 needs_human。",
      "timeline": [
        {
          "state": "done",
          "label": "PATCH APPLIED",
          "detail": "候选 Diff 通过策略并写入一次性工作副本。"
        },
        {
          "state": "checkpoint",
          "label": "CHECKPOINT",
          "detail": "SQLite 已保存 apply_patch 成功结果和修改文件 SHA-256。"
        },
        {
          "state": "crash",
          "label": "PROCESS EXIT",
          "detail": "在目标测试启动前中断，任务状态持久化为 interrupted。"
        },
        {
          "state": "resume",
          "label": "RESTART",
          "detail": "新进程读取 patch_applied checkpoint 并验证工作副本完整性。"
        },
        {
          "state": "skip",
          "label": "SKIP COMPLETED",
          "detail": "模型调用为 0，apply_patch 不重复执行。"
        },
        {
          "state": "pass",
          "label": "VERIFY",
          "detail": "只执行目标测试与完整回归，随后进入 awaiting_review。"
        }
      ]
    }
  ]
};
