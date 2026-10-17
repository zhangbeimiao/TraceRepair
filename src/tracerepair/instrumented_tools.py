"""TraceStore-backed adapters for bounded repository tools."""

import hashlib
from pathlib import Path
from uuid import uuid4

from tracerepair.models import TaskStatus
from tracerepair.patch_apply import PatchApplier, PatchApplyResult
from tracerepair.patch_policy import PatchPolicy
from tracerepair.read_tools import FileSlice, ReadOnlyRepository, ReadOnlyResult
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner, TestRunResult


class InstrumentedTools:
    """Record tool lifecycle events without persisting bulky source or log bodies."""

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        repository: ReadOnlyRepository,
        test_runner: RestrictedTestRunner,
        patch_applier: PatchApplier | None = None,
    ) -> None:
        task = store.get_task(task_id)
        if task.status is not TaskStatus.RUNNING:
            raise ValueError("tools may only be attached to a running task")
        self._task_id = task_id
        self._store = store
        self._repository = repository
        self._test_runner = test_runner
        self._patch_applier = patch_applier

    def repo_map(self, max_files: int = 100) -> ReadOnlyResult[list]:
        call_id = self._start("repo_map", {"max_files": max_files})
        result = self._repository.repo_map(max_files)
        self._finish(call_id, "repo_map", result, self._map_summary(result))
        return result

    def search_code(self, query: str, max_hits: int | None = None) -> ReadOnlyResult[list]:
        arguments = {"query": query, "max_hits": max_hits}
        call_id = self._start("search_code", arguments)
        result = self._repository.search_code(query, max_hits)
        self._finish(call_id, "search_code", result, self._search_summary(result))
        return result

    def read_file(
        self, path: str, start_line: int = 1, end_line: int | None = None
    ) -> ReadOnlyResult[FileSlice]:
        arguments = {"path": path, "start_line": start_line, "end_line": end_line}
        call_id = self._start("read_file", arguments)
        result = self._repository.read_file(path, start_line, end_line)
        self._finish(call_id, "read_file", result, self._read_summary(result))
        return result

    def run_tests(self, selector: str) -> TestRunResult:
        call_id = self._start("run_tests", {"selector": selector})
        result = self._test_runner.run_tests(selector)
        summary = {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
            "error_code": result.error_code,
            "stdout_sha256": self._digest(result.stdout),
            "stderr_sha256": self._digest(result.stderr),
            "output_truncated": result.output_truncated,
        }
        self._finish(call_id, "run_tests", result, summary)
        return result

    def run_regression(self) -> TestRunResult:
        call_id = self._start("run_regression", {"suite": "tests"})
        result = self._test_runner.run_regression()
        summary = {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
            "error_code": result.error_code,
            "stdout_sha256": self._digest(result.stdout),
            "stderr_sha256": self._digest(result.stderr),
            "output_truncated": result.output_truncated,
        }
        self._finish(call_id, "run_regression", result, summary)
        return result

    def apply_patch(self, unified_diff: str) -> PatchApplyResult:
        call_id = self._start("apply_patch", {"diff_sha256": self._digest(unified_diff)})
        if self._patch_applier is None:
            result = PatchApplyResult(
                False,
                "PATCH_APPLIER_UNAVAILABLE",
                (),
                {},
                PatchPolicy().validate(""),
            )
        else:
            result = self._patch_applier.apply(unified_diff)
        summary = {
            "files": list(result.files),
            "file_sha256": result.file_sha256,
            "validation_errors": list(result.validation.errors),
        }
        self._finish(call_id, "apply_patch", result, summary)
        return result

    def _start(self, tool_name: str, arguments: dict[str, object]) -> str:
        call_id = str(uuid4())
        self._store.append_event(
            self._task_id,
            "tool_started",
            {"call_id": call_id, "tool": tool_name, "arguments": arguments},
        )
        return call_id

    def _finish(self, call_id: str, tool_name: str, result: object, summary: dict[str, object]) -> None:
        ok = bool(getattr(result, "ok", False))
        error = getattr(result, "error", None)
        error_code = getattr(error, "code", None) or getattr(result, "error_code", None)
        payload = {
            "call_id": call_id,
            "tool": tool_name,
            "ok": ok,
            "error_code": error_code,
            "summary": summary,
        }
        self._store.append_event(self._task_id, "tool_finished", payload)
        checkpoint = self._store.load_checkpoint(self._task_id)
        completed = list(checkpoint.get("completed_tools", []))[-19:]
        completed.append({"call_id": call_id, "tool": tool_name, "ok": ok})
        checkpoint["completed_tools"] = completed
        checkpoint["last_tool"] = payload
        self._store.save_checkpoint(self._task_id, checkpoint)

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _map_summary(result: ReadOnlyResult[list]) -> dict[str, object]:
        return {"file_count": len(result.data or [])}

    @staticmethod
    def _search_summary(result: ReadOnlyResult[list]) -> dict[str, object]:
        hits = result.data or []
        return {"hit_count": len(hits), "paths": list(dict.fromkeys(hit.path for hit in hits))[:10]}

    @staticmethod
    def _read_summary(result: ReadOnlyResult[FileSlice]) -> dict[str, object]:
        if result.data is None:
            return {}
        return {
            "path": result.data.path,
            "start_line": result.data.start_line,
            "end_line": result.data.end_line,
            "content_sha256": InstrumentedTools._digest(result.data.content),
        }
