"""Bounded end-to-end model workflow built on TraceRepair's existing gates."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner
from tracerepair.models import TaskStatus
from tracerepair.read_tools import FileSlice, ReadOnlyResult
from tracerepair.recovery import (
    PATCH_APPLIED,
    SOURCE_READ,
    TARGET_PASSED,
    RecoveryError,
    inject_crash_if_requested,
    load_source_checkpoint,
    mark_recovery_phase,
    recovery_state,
    save_source_checkpoint,
)
from tracerepair.store import TraceStore
from tracerepair.workflow import CandidateRepairWorkflow


_READ_ONLY = {"repo_map", "search_code", "read_file"}


@dataclass(frozen=True)
class EndToEndResult:
    action: str
    task_status: TaskStatus
    detail: str
    diagnosis_turns: int
    completion_tokens: int


class EndToEndRepairWorkflow:
    """Diagnose with read-only tools, then verify one model-proposed patch.

    The model never receives a write or shell tool.  Its candidate diff is
    passed to CandidateRepairWorkflow, which owns patch policy, target tests,
    regression tests, and the final human-review transition.
    """

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        planner: ModelPlanner,
        tools: InstrumentedTools,
        *,
        target_selector: str | None = None,
        allowed_source_roots: tuple[str, ...] = ("src/eventrelay",),
        max_diagnosis_turns: int = 3,
        crash_after: str | None = None,
    ) -> None:
        if not 1 <= max_diagnosis_turns <= 5:
            raise ValueError("max_diagnosis_turns must be between 1 and 5")
        self._task_id = task_id
        self._store = store
        self._planner = planner
        self._tools = tools
        self._repair = CandidateRepairWorkflow(
            task_id,
            store,
            tools,
            target_selector=target_selector,
            allowed_source_roots=allowed_source_roots,
            crash_after=crash_after,
        )
        self._allowed_source_roots = allowed_source_roots
        self._max_diagnosis_turns = max_diagnosis_turns
        self._crash_after = crash_after

    def run(
        self,
        issue: str,
        *,
        diagnostic_queries: tuple[str, ...] = (),
        resume: bool = False,
    ) -> EndToEndResult:
        task = self._store.get_task(self._task_id)
        if task.status is not TaskStatus.RUNNING:
            raise ValueError("end-to-end workflow requires a running task")

        if resume:
            return self._resume(issue)

        self._store.append_event(self._task_id, "workflow_phase_changed", {"phase": "diagnosis"})
        evidence = (
            f"Task: {issue}. Diagnose before repair. Search for distinctive source-code "
            "identifiers or literals, not the task title or case number. Choose one action only. "
            "Never guess a path: read_file paths must come from repo_map or search results. "
            "Never request patches or tests during this read-only phase. "
            f"Public entrypoint hints from the failing test: {', '.join(diagnostic_queries) or 'none'}."
        )
        allowed_tools = {"repo_map", "search_code"}
        seen_actions: set[str] = set()
        total_tokens = 0
        source: FileSlice | None = None

        for turn in range(1, self._max_diagnosis_turns + 1):
            plan = self._planner.suggest(
                self._task_id,
                self._store,
                evidence,
                allowed_tools=allowed_tools,
                allow_patch=False,
            )
            total_tokens += plan.completion_tokens
            if plan.kind == "handoff":
                return self._stop("handoff", plan.reason or "model requested handoff", turn, total_tokens)
            if plan.kind != "tool" or plan.tool not in _READ_ONLY:
                return self._stop("diagnosis", "model left the read-only stage", turn, total_tokens)

            action_key = f"{plan.tool}:{json.dumps(plan.arguments, sort_keys=True)}"
            if action_key in seen_actions:
                return self._stop("diagnosis", "model repeated the same tool action", turn, total_tokens)
            seen_actions.add(action_key)

            result = self._execute(plan.tool, plan.arguments)
            if not result.ok:
                code = result.error.code if result.error else "READ_TOOL_FAILED"
                return self._stop(plan.tool, code, turn, total_tokens)
            if isinstance(result.data, FileSlice):
                if _source_is_relevant(issue, result.data, diagnostic_queries):
                    source = result.data
                    diagnosis_turns = turn
                    break
                recovered = self._recover_from_queries(
                    issue, diagnostic_queries, "irrelevant_source"
                )
                if recovered is not None:
                    source = recovered
                    diagnosis_turns = turn
                    break
                fallback_query = _first_diagnostic_query(issue, diagnostic_queries)
                if fallback_query is not None:
                    evidence = (
                        f"Original task: {issue}. The file {result.data.path} did not contain the "
                        f"quoted task literal {fallback_query!r}, so it is not sufficient repair "
                        "evidence. Search for a more specific observed identifier; do not return "
                        "to the previous file."
                    )
                    allowed_tools = {"repo_map", "search_code"}
                else:
                    allowed_tools = {"repo_map", "search_code"}
                    evidence = (
                        f"Original task: {issue}. The file {result.data.path} was not sufficient "
                        "repair evidence. Search for a more specific identifier or return handoff."
                    )
                continue

            if plan.tool == "search_code" and turn == self._max_diagnosis_turns:
                recovered = self._read_unique_search_result(
                    result, issue, diagnostic_queries, "diagnosis_budget"
                )
                if recovered is not None:
                    source = recovered
                    diagnosis_turns = turn
                    break

            allowed_tools = _next_allowed_tools(plan.tool, result)
            refinement = (
                " The result spans too many files; refine with a code identifier or literal before "
                "reading a file."
                if plan.tool == "search_code" and allowed_tools == {"search_code"}
                else ""
            )
            evidence = (
                f"Original task: {issue}. Previous action: {plan.tool} with arguments "
                f"{json.dumps(plan.arguments, ensure_ascii=False)}. Observation: {_summarize(result)}. "
                "Choose one next read-only action. Use read_file only with an exact observed path. "
                f"If no result is relevant, return handoff.{refinement}"
            )
        else:
            recovered = self._recover_from_queries(
                issue, diagnostic_queries, "diagnosis_exhausted"
            )
            if recovered is not None:
                source = recovered
                diagnosis_turns = self._max_diagnosis_turns
            else:
                return self._stop(
                    "diagnosis",
                    "diagnosis budget ended before a source file was read",
                    self._max_diagnosis_turns,
                    total_tokens,
                )

        if source is None:
            return self._stop(
                "diagnosis",
                "diagnosis budget ended before a source file was read",
                self._max_diagnosis_turns,
                total_tokens,
            )

        save_source_checkpoint(
            self._task_id,
            self._store,
            Path(task.workspace),
            source,
            diagnosis_turns=diagnosis_turns,
        )
        inject_crash_if_requested(
            self._task_id,
            self._store,
            configured_point=self._crash_after,
            reached_point=SOURCE_READ,
        )
        return self._generate_and_verify(issue, source, diagnosis_turns, total_tokens)

    def _resume(self, issue: str) -> EndToEndResult:
        checkpoint = self._store.load_checkpoint(self._task_id)
        try:
            state = recovery_state(checkpoint)
        except RecoveryError as error:
            return self._stop("resume", str(error), 0, _checkpoint_tokens(checkpoint))
        phase = state.get("phase")
        turns = state.get("diagnosis_turns", 0)
        diagnosis_turns = turns if isinstance(turns, int) else 0
        total_tokens = _checkpoint_tokens(checkpoint)
        completed = checkpoint.get("completed_tools", [])
        skipped_tools = [
            str(item.get("tool"))
            for item in completed
            if isinstance(item, dict) and item.get("ok") is True
        ]
        self._store.append_event(
            self._task_id,
            "workflow_resumed",
            {"phase": phase, "skipped_tools": skipped_tools},
        )
        apply_state = self._tool_call_state("apply_patch")
        if apply_state == "unfinished":
            return self._stop(
                "resume",
                "patch application was interrupted before a durable result",
                diagnosis_turns,
                total_tokens,
            )
        if apply_state == "failed":
            return self._stop(
                "resume",
                "completed patch application was rejected",
                diagnosis_turns,
                total_tokens,
            )
        if phase == SOURCE_READ and apply_state == "success":
            # A real process may exit after tool_finished commits but before the
            # following phase marker. Reconcile from the durable tool result.
            mark_recovery_phase(self._task_id, self._store, PATCH_APPLIED)
            self._store.append_event(
                self._task_id,
                "recovery_checkpoint_reconciled",
                {"from_phase": SOURCE_READ, "to_phase": PATCH_APPLIED},
            )
            phase = PATCH_APPLIED
        if phase == SOURCE_READ:
            try:
                source, diagnosis_turns = load_source_checkpoint(
                    self._task_id,
                    self._store,
                    Path(self._store.get_task(self._task_id).workspace),
                    allowed_source_roots=self._allowed_source_roots,
                )
            except RecoveryError as error:
                return self._stop("resume", str(error), diagnosis_turns, total_tokens)
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {
                    "stage": "diagnosis",
                    "tools": skipped_tools,
                    "reason": "restored verified source artifact",
                },
            )
            return self._generate_and_verify(issue, source, diagnosis_turns, total_tokens)
        if phase in {PATCH_APPLIED, TARGET_PASSED}:
            repair = self._repair.resume()
            return EndToEndResult(
                repair.action,
                repair.task_status,
                repair.detail,
                diagnosis_turns,
                total_tokens,
            )
        return self._stop(
            "resume",
            "checkpoint does not contain a resumable phase",
            diagnosis_turns,
            total_tokens,
        )

    def _tool_call_state(self, tool: str) -> str | None:
        events = self._store.list_events(self._task_id)
        starts = {
            str(event.payload.get("call_id"))
            for event in events
            if event.event_type == "tool_started" and event.payload.get("tool") == tool
        }
        finishes = [
            event.payload
            for event in events
            if event.event_type == "tool_finished" and event.payload.get("tool") == tool
        ]
        finished_ids = {str(payload.get("call_id")) for payload in finishes}
        if starts - finished_ids:
            return "unfinished"
        if not finishes:
            return None
        return "success" if finishes[-1].get("ok") is True else "failed"

    def _generate_and_verify(
        self,
        issue: str,
        source: FileSlice,
        diagnosis_turns: int,
        total_tokens: int,
    ) -> EndToEndResult:
        self._store.append_event(
            self._task_id,
            "workflow_phase_changed",
            {"phase": "patch_generation", "source_path": source.path},
        )
        patch_evidence = (
            f"Task: {issue}.\n"
            f"Confirmed source path: {source.path}\n"
            "Return one smallest unified diff against that exact path, or handoff if the evidence is "
            "insufficient. Never edit tests. Copy context and removed lines exactly from Source; "
            "include at least three unchanged context lines around the edit.\n"
            f"Source:\n{source.content}"
        )
        patch_plan = self._planner.suggest(
            self._task_id,
            self._store,
            patch_evidence,
            allowed_tools=set(),
            allow_patch=True,
        )
        total_tokens += patch_plan.completion_tokens
        if patch_plan.kind != "patch":
            return self._stop(
                "handoff",
                patch_plan.reason or "model declined to produce a patch",
                diagnosis_turns,
                total_tokens,
            )

        self._store.transition(
            self._task_id,
            TaskStatus.NEEDS_HUMAN,
            "model candidate requires controlled verification",
        )
        repair = self._repair.submit_candidate(patch_plan.unified_diff or "")
        return EndToEndResult(
            repair.action,
            repair.task_status,
            repair.detail,
            diagnosis_turns,
            total_tokens,
        )

    def _stop(
        self, action: str, detail: str, diagnosis_turns: int, completion_tokens: int
    ) -> EndToEndResult:
        if self._store.get_task(self._task_id).status is TaskStatus.RUNNING:
            self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, detail)
        return EndToEndResult(
            action,
            TaskStatus.NEEDS_HUMAN,
            detail,
            diagnosis_turns,
            completion_tokens,
        )

    def _execute(self, tool: str, arguments: dict[str, object]) -> ReadOnlyResult:
        if tool == "repo_map":
            return self._tools.repo_map(_bounded_int(arguments.get("max_files"), 100, 1, 100))
        if tool == "search_code":
            query = arguments.get("query")
            if not isinstance(query, str) or not 2 <= len(query) <= 200:
                return ReadOnlyResult.failure("INVALID_PLAN", "invalid search query")
            return self._tools.search_code(
                query, _bounded_int(arguments.get("max_hits"), 20, 1, 30)
            )
        path = arguments.get("path")
        if not isinstance(path, str) or len(path) > 300:
            return ReadOnlyResult.failure("INVALID_PLAN", "invalid read path")
        return self._tools.read_file(
            path,
            _bounded_int(arguments.get("start_line"), 1, 1, 10_000),
            _bounded_int(arguments.get("end_line"), 200, 1, 10_000),
        )

    def _read_unique_search_result(
        self,
        result: ReadOnlyResult,
        issue: str,
        diagnostic_queries: tuple[str, ...],
        trigger: str,
    ) -> FileSlice | None:
        path = _unique_hit_path(result)
        if path is None:
            return None
        read = self._tools.read_file(path, 1, 200)
        if not read.ok or not isinstance(read.data, FileSlice):
            return None
        if not _source_is_relevant(issue, read.data, diagnostic_queries):
            return None
        self._store.append_event(
            self._task_id,
            "deterministic_recovery",
            {"trigger": trigger, "action": "read_file", "path": path},
        )
        return read.data

    def _recover_from_queries(
        self, issue: str, diagnostic_queries: tuple[str, ...], trigger: str
    ) -> FileSlice | None:
        for query in _diagnostic_queries(issue, diagnostic_queries):
            search = self._tools.search_code(query, 20)
            if not search.ok:
                continue
            recovered = self._read_unique_search_result(
                search, issue, diagnostic_queries, trigger
            )
            if recovered is not None:
                return recovered
        return None


def _next_allowed_tools(tool: str, result: ReadOnlyResult) -> set[str]:
    if not result.data:
        return {"repo_map", "search_code"}
    if tool == "repo_map":
        return {"read_file"}
    if tool == "search_code":
        hits = result.data or []
        paths = {getattr(hit, "path", None) for hit in hits}
        if len(hits) >= 8 or len(paths) > 3:
            return {"search_code"}
        return {"search_code", "read_file"}
    return _READ_ONLY


def _summarize(result: ReadOnlyResult) -> str:
    items = result.data or []
    return "items: " + (", ".join(str(item)[:180] for item in items[:8]) if items else "none")


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return min(max(value, minimum), maximum)


def _checkpoint_tokens(checkpoint: dict[str, object]) -> int:
    budget = checkpoint.get("model_budget", {})
    if not isinstance(budget, dict):
        return 0
    value = budget.get("completion_tokens", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _quoted_literal(issue: str) -> str | None:
    matches = re.findall(r"['\"]([^'\"]{2,50})['\"]", issue)
    return matches[0] if matches else None


def _source_is_relevant(
    issue: str, source: FileSlice, diagnostic_queries: tuple[str, ...] = ()
) -> bool:
    markers = _diagnostic_queries(issue, diagnostic_queries)
    if not markers:
        return True
    haystack = f"{source.path}\n{source.content}".casefold()
    return any(marker.casefold() in haystack for marker in markers)


def _unique_hit_path(result: ReadOnlyResult) -> str | None:
    hits = result.data or []
    paths = {getattr(hit, "path", None) for hit in hits}
    paths.discard(None)
    if len(paths) != 1:
        return None
    return str(next(iter(paths)))


def _diagnostic_queries(issue: str, configured: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    literal = _quoted_literal(issue)
    if literal is not None:
        values.append(literal)
    values.extend(query for query in configured if 2 <= len(query) <= 200)
    return tuple(dict.fromkeys(values))


def _first_diagnostic_query(issue: str, configured: tuple[str, ...]) -> str | None:
    queries = _diagnostic_queries(issue, configured)
    return queries[0] if queries else None
