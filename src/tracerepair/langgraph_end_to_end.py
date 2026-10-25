"""Complete LangGraph orchestration for the bounded repair agent.

LangGraph owns only in-process routing. SQLite ``TraceStore`` remains the sole
durable source of task status, checkpoints, budgets, and trace events. The
graph is intentionally compiled without a LangGraph checkpointer so recovery
always reconstructs routing from verified SQLite state.
"""

from __future__ import annotations

import hashlib
import json
import operator
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from tracerepair.end_to_end_workflow import (
    EndToEndResult,
    _bounded_int,
    _checkpoint_tokens,
    _diagnostic_queries,
    _first_diagnostic_query,
    _next_allowed_tools,
    _source_is_relevant,
    _summarize,
    _unique_hit_window,
)
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
from tracerepair.repository_task import is_allowed_source_path
from tracerepair.store import TraceStore
from tracerepair.workflow import case_selector


_READ_ONLY = {"repo_map", "search_code", "read_file"}


class RepairGraphState(TypedDict, total=False):
    """Ephemeral state passed between graph nodes; never used as a checkpoint."""

    task_id: str
    issue: str
    diagnostic_queries: tuple[str, ...]
    resume: bool
    evidence: str
    allowed_tools: tuple[str, ...]
    seen_actions: list[str]
    diagnosis_turns: int
    completion_tokens: int
    source: FileSlice | None
    candidate: str
    action: str
    detail: str
    task_status: str
    next_node: str
    node_history: Annotated[list[str], operator.add]


class LangGraphEndToEndRepairWorkflow:
    """Run diagnosis, patching, verification, and recovery as explicit graph nodes."""

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
        self._target_selector = target_selector
        self._allowed_source_roots = allowed_source_roots
        self._max_diagnosis_turns = max_diagnosis_turns
        self._crash_after = crash_after
        self._graph = self._build_graph()

    @property
    def graph(self):
        """Expose the compiled graph for inspection and architecture tests."""

        return self._graph

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

        initial: RepairGraphState = {
            "task_id": self._task_id,
            "issue": issue,
            "diagnostic_queries": diagnostic_queries,
            "resume": resume,
            "evidence": self._initial_evidence(issue, diagnostic_queries),
            "allowed_tools": ("repo_map", "search_code"),
            "seen_actions": [],
            "diagnosis_turns": 0,
            "completion_tokens": _checkpoint_tokens(self._store.load_checkpoint(self._task_id))
            if resume
            else 0,
            "source": None,
            "candidate": "",
            "action": "resume" if resume else "diagnosis",
            "detail": "graph invoked",
            "task_status": task.status.value,
            "next_node": "resume" if resume else "diagnose",
            "node_history": [],
        }
        result = self._graph.invoke(initial, {"recursion_limit": 24})
        final_task = self._store.get_task(self._task_id)
        return EndToEndResult(
            str(result.get("action", "stop")),
            final_task.status,
            str(result.get("detail", "workflow stopped")),
            int(result.get("diagnosis_turns", 0)),
            int(result.get("completion_tokens", 0)),
        )

    def _build_graph(self):
        graph = StateGraph(RepairGraphState)
        graph.add_node("resume", self._resume)
        graph.add_node("diagnose", self._diagnose)
        graph.add_node("checkpoint_source", self._checkpoint_source)
        graph.add_node("generate_patch", self._generate_patch)
        graph.add_node("apply_patch", self._apply_patch)
        graph.add_node("run_target", self._run_target)
        graph.add_node("run_regression", self._run_regression)
        graph.add_conditional_edges(
            START,
            lambda state: "resume" if state.get("resume") else "diagnose",
            {"resume": "resume", "diagnose": "diagnose"},
        )
        graph.add_conditional_edges(
            "resume",
            self._route_next,
            {
                "generate_patch": "generate_patch",
                "run_target": "run_target",
                "run_regression": "run_regression",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "diagnose",
            self._route_after_diagnosis,
            {"diagnose": "diagnose", "checkpoint_source": "checkpoint_source", "end": END},
        )
        graph.add_edge("checkpoint_source", "generate_patch")
        graph.add_conditional_edges(
            "generate_patch", self._route_next, {"apply_patch": "apply_patch", "end": END}
        )
        graph.add_conditional_edges(
            "apply_patch", self._route_next, {"run_target": "run_target", "end": END}
        )
        graph.add_conditional_edges(
            "run_target",
            self._route_next,
            {"run_regression": "run_regression", "end": END},
        )
        graph.add_edge("run_regression", END)
        # Deliberately no LangGraph checkpointer: SQLite is the only durable state.
        return graph.compile()

    def _route_after_diagnosis(self, state: RepairGraphState) -> str:
        if self._store.get_task(self._task_id).status is not TaskStatus.RUNNING:
            return "end"
        return "checkpoint_source" if state.get("source") is not None else "diagnose"

    @staticmethod
    def _route_next(state: RepairGraphState) -> str:
        return str(state.get("next_node", "end"))

    def _diagnose(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("diagnose")
        if int(state.get("diagnosis_turns", 0)) == 0:
            self._store.append_event(
                self._task_id, "workflow_phase_changed", {"phase": "diagnosis"}
            )
        turn = int(state.get("diagnosis_turns", 0)) + 1
        total_tokens = int(state.get("completion_tokens", 0))
        allowed_tools = set(state.get("allowed_tools", ("repo_map", "search_code")))
        plan = self._planner.suggest(
            self._task_id,
            self._store,
            str(state["evidence"]),
            allowed_tools=allowed_tools,
            allow_patch=False,
        )
        total_tokens += plan.completion_tokens
        if plan.kind == "handoff":
            return self._stop_node(
                "diagnose", "handoff", plan.reason or "model requested handoff", turn, total_tokens
            )
        if plan.kind != "tool" or plan.tool not in _READ_ONLY:
            return self._stop_node(
                "diagnose", "diagnosis", "model left the read-only stage", turn, total_tokens
            )

        diagnostic_queries = tuple(state.get("diagnostic_queries", ()))
        issue = str(state["issue"])
        action_key = f"{plan.tool}:{json.dumps(plan.arguments, sort_keys=True)}"
        seen_actions = list(state.get("seen_actions", []))
        if action_key in seen_actions:
            source = self._recover_from_queries(issue, diagnostic_queries, "repeated_action")
            if source is None:
                return self._stop_node(
                    "diagnose", "diagnosis", "model repeated the same tool action", turn, total_tokens
                )
            return self._complete_node(
                "diagnose",
                {
                    "source": source,
                    "diagnosis_turns": turn,
                    "completion_tokens": total_tokens,
                    "action": plan.tool,
                    "detail": "deterministic recovery located source",
                    "seen_actions": seen_actions,
                    "node_history": ["diagnose"],
                },
            )
        seen_actions.append(action_key)

        result = self._execute(plan.tool, plan.arguments)
        if not result.ok:
            code = result.error.code if result.error else "READ_TOOL_FAILED"
            return self._stop_node("diagnose", plan.tool, code, turn, total_tokens)
        if isinstance(result.data, FileSlice):
            if _source_is_relevant(issue, result.data, diagnostic_queries):
                return self._complete_node(
                    "diagnose",
                    {
                        "source": result.data,
                        "diagnosis_turns": turn,
                        "completion_tokens": total_tokens,
                        "seen_actions": seen_actions,
                        "action": plan.tool,
                        "detail": "relevant source located",
                        "node_history": ["diagnose"],
                    },
                )
            source = self._recover_from_queries(issue, diagnostic_queries, "irrelevant_source")
            if source is not None:
                return self._complete_node(
                    "diagnose",
                    {
                        "source": source,
                        "diagnosis_turns": turn,
                        "completion_tokens": total_tokens,
                        "seen_actions": seen_actions,
                        "action": plan.tool,
                        "detail": "deterministic recovery replaced irrelevant source",
                        "node_history": ["diagnose"],
                    },
                )
            fallback_query = _first_diagnostic_query(issue, diagnostic_queries)
            evidence = (
                f"Original task: {issue}. The file {result.data.path} did not contain the "
                f"quoted task literal {fallback_query!r}, so it is not sufficient repair evidence. "
                "Search for a more specific observed identifier; do not return to the previous file."
                if fallback_query is not None
                else f"Original task: {issue}. The file {result.data.path} was not sufficient "
                "repair evidence. Search for a more specific identifier or return handoff."
            )
            return self._continue_diagnosis(
                turn, total_tokens, seen_actions, evidence, ("repo_map", "search_code"), issue,
                diagnostic_queries,
            )

        if plan.tool == "search_code" and turn == self._max_diagnosis_turns:
            source = self._read_unique_search_result(
                result, issue, diagnostic_queries, "diagnosis_budget"
            )
            if source is not None:
                return self._complete_node(
                    "diagnose",
                    {
                        "source": source,
                        "diagnosis_turns": turn,
                        "completion_tokens": total_tokens,
                        "seen_actions": seen_actions,
                        "action": plan.tool,
                        "detail": "unique search result located source",
                        "node_history": ["diagnose"],
                    },
                )

        next_tools = _next_allowed_tools(plan.tool, result)
        refinement = (
            " The result spans too many files; refine with a code identifier or literal before "
            "reading a file."
            if plan.tool == "search_code" and next_tools == {"search_code"}
            else ""
        )
        evidence = (
            f"Original task: {issue}. Previous action: {plan.tool} with arguments "
            f"{json.dumps(plan.arguments, ensure_ascii=False)}. Observation: {_summarize(result)}. "
            "Choose one next read-only action. Use read_file only with an exact observed path. "
            f"If no result is relevant, return handoff.{refinement}"
        )
        return self._continue_diagnosis(
            turn,
            total_tokens,
            seen_actions,
            evidence,
            tuple(sorted(next_tools)),
            issue,
            diagnostic_queries,
        )

    def _continue_diagnosis(
        self,
        turn: int,
        total_tokens: int,
        seen_actions: list[str],
        evidence: str,
        allowed_tools: tuple[str, ...],
        issue: str,
        diagnostic_queries: tuple[str, ...],
    ) -> dict[str, object]:
        if turn >= self._max_diagnosis_turns:
            source = self._recover_from_queries(issue, diagnostic_queries, "diagnosis_exhausted")
            if source is not None:
                return self._complete_node(
                    "diagnose",
                    {
                        "source": source,
                        "diagnosis_turns": turn,
                        "completion_tokens": total_tokens,
                        "seen_actions": seen_actions,
                        "action": "diagnosis",
                        "detail": "diagnosis fallback located source",
                        "node_history": ["diagnose"],
                    },
                )
            return self._stop_node(
                "diagnose",
                "diagnosis",
                "diagnosis budget ended before a source file was read",
                turn,
                total_tokens,
            )
        return self._complete_node(
            "diagnose",
            {
                "evidence": evidence,
                "allowed_tools": allowed_tools,
                "seen_actions": seen_actions,
                "diagnosis_turns": turn,
                "completion_tokens": total_tokens,
                "action": "diagnosis",
                "detail": "diagnosis continues",
                "node_history": ["diagnose"],
            },
        )

    def _checkpoint_source(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("checkpoint_source")
        source = state.get("source")
        if not isinstance(source, FileSlice):
            return self._stop_node(
                "checkpoint_source",
                "diagnosis",
                "source checkpoint requested without source evidence",
                int(state.get("diagnosis_turns", 0)),
                int(state.get("completion_tokens", 0)),
            )
        task = self._store.get_task(self._task_id)
        save_source_checkpoint(
            self._task_id,
            self._store,
            Path(task.workspace),
            source,
            diagnosis_turns=int(state["diagnosis_turns"]),
        )
        inject_crash_if_requested(
            self._task_id,
            self._store,
            configured_point=self._crash_after,
            reached_point=SOURCE_READ,
        )
        return self._complete_node(
            "checkpoint_source",
            {
                "next_node": "generate_patch",
                "action": "checkpoint_source",
                "detail": "source checkpoint persisted",
                "node_history": ["checkpoint_source"],
            },
        )

    def _generate_patch(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("generate_patch")
        source = state.get("source")
        if not isinstance(source, FileSlice):
            return self._stop_node(
                "generate_patch",
                "patch_generation",
                "patch generation has no verified source",
                int(state.get("diagnosis_turns", 0)),
                int(state.get("completion_tokens", 0)),
            )
        self._store.append_event(
            self._task_id,
            "workflow_phase_changed",
            {"phase": "patch_generation", "source_path": source.path},
        )
        patch_plan = self._planner.suggest(
            self._task_id,
            self._store,
            self._patch_evidence(str(state["issue"]), source),
            allowed_tools=set(),
            allow_patch=True,
        )
        total_tokens = int(state.get("completion_tokens", 0)) + patch_plan.completion_tokens
        if patch_plan.kind != "patch":
            return self._stop_node(
                "generate_patch",
                "handoff",
                patch_plan.reason or "model declined to produce a patch",
                int(state.get("diagnosis_turns", 0)),
                total_tokens,
            )
        candidate = patch_plan.unified_diff or ""
        try:
            self._persist_candidate(candidate)
        except OSError:
            return self._stop_node(
                "generate_patch",
                "candidate_artifact",
                "candidate diff could not be persisted for audit",
                int(state.get("diagnosis_turns", 0)),
                total_tokens,
            )
        self._store.transition(
            self._task_id,
            TaskStatus.NEEDS_HUMAN,
            "model candidate requires controlled verification",
        )
        return self._complete_node(
            "generate_patch",
            {
                "candidate": candidate,
                "completion_tokens": total_tokens,
                "next_node": "apply_patch",
                "action": "generate_patch",
                "detail": "candidate persisted; deterministic verification required",
                "task_status": TaskStatus.NEEDS_HUMAN.value,
                "node_history": ["generate_patch"],
            },
        )

    def _apply_patch(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("apply_patch")
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.NEEDS_HUMAN:
            self._store.transition(self._task_id, TaskStatus.READY, "graph accepted candidate for verification")
            self._store.transition(self._task_id, TaskStatus.RUNNING, "deterministic verification started")
        candidate = str(state.get("candidate", ""))
        applied = self._tools.apply_patch(candidate)
        if not applied.ok:
            return self._stop_node(
                "apply_patch",
                "apply_patch",
                applied.error_code or "rejected",
                int(state.get("diagnosis_turns", 0)),
                int(state.get("completion_tokens", 0)),
                transition_reason=f"candidate patch rejected: {applied.error_code}",
            )
        mark_recovery_phase(self._task_id, self._store, PATCH_APPLIED)
        inject_crash_if_requested(
            self._task_id,
            self._store,
            configured_point=self._crash_after,
            reached_point=PATCH_APPLIED,
        )
        return self._complete_node(
            "apply_patch",
            {
                "next_node": "run_target",
                "action": "apply_patch",
                "detail": "candidate applied to disposable workspace",
                "task_status": TaskStatus.RUNNING.value,
                "node_history": ["apply_patch"],
            },
        )

    def _run_target(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("run_target")
        previous = self._latest_tool_result("run_tests")
        if previous is None:
            result = self._tools.run_tests(self._selector())
            if not result.ok:
                return self._stop_node(
                    "run_target",
                    "run_tests",
                    result.error_code or "failed",
                    int(state.get("diagnosis_turns", 0)),
                    int(state.get("completion_tokens", 0)),
                    transition_reason=f"candidate patch failed target test: {result.error_code}",
                )
            mark_recovery_phase(self._task_id, self._store, TARGET_PASSED)
        elif previous.get("ok") is True:
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {"tool": "run_tests", "reason": "verified completed tool result"},
            )
            mark_recovery_phase(self._task_id, self._store, TARGET_PASSED)
        else:
            code = str(previous.get("error_code") or "failed")
            return self._stop_node(
                "run_target",
                "run_tests",
                code,
                int(state.get("diagnosis_turns", 0)),
                int(state.get("completion_tokens", 0)),
                transition_reason=f"candidate patch failed target test: {code}",
            )
        return self._complete_node(
            "run_target",
            {
                "next_node": "run_regression",
                "action": "run_tests",
                "detail": "target test passed",
                "node_history": ["run_target"],
            },
        )

    def _run_regression(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("run_regression")
        previous = self._latest_tool_result("run_regression")
        if previous is None:
            result = self._tools.run_regression()
            if not result.ok:
                return self._stop_node(
                    "run_regression",
                    "run_regression",
                    result.error_code or "failed",
                    int(state.get("diagnosis_turns", 0)),
                    int(state.get("completion_tokens", 0)),
                    transition_reason=f"candidate patch failed regression: {result.error_code}",
                )
        elif previous.get("ok") is True:
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {"tool": "run_regression", "reason": "verified completed tool result"},
            )
        else:
            code = str(previous.get("error_code") or "failed")
            return self._stop_node(
                "run_regression",
                "run_regression",
                code,
                int(state.get("diagnosis_turns", 0)),
                int(state.get("completion_tokens", 0)),
                transition_reason=f"candidate patch failed regression: {code}",
            )
        self._store.transition(
            self._task_id,
            TaskStatus.AWAITING_REVIEW,
            "candidate patch passed target and regression tests; human review required",
        )
        return self._complete_node(
            "run_regression",
            {
                "next_node": "end",
                "action": "run_regression",
                "detail": "all tests passed",
                "task_status": TaskStatus.AWAITING_REVIEW.value,
                "node_history": ["run_regression"],
            },
        )

    def _resume(self, state: RepairGraphState) -> dict[str, object]:
        self._node_started("resume")
        checkpoint = self._store.load_checkpoint(self._task_id)
        try:
            recovery = recovery_state(checkpoint)
        except RecoveryError as error:
            return self._stop_node(
                "resume", "resume", str(error), 0, _checkpoint_tokens(checkpoint)
            )
        phase = recovery.get("phase")
        turns = recovery.get("diagnosis_turns", 0)
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
            return self._stop_node(
                "resume",
                "resume",
                "patch application was interrupted before a durable result",
                diagnosis_turns,
                total_tokens,
            )
        if apply_state == "failed":
            return self._stop_node(
                "resume",
                "resume",
                "completed patch application was rejected",
                diagnosis_turns,
                total_tokens,
            )
        if phase == SOURCE_READ and apply_state == "success":
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
                return self._stop_node(
                    "resume", "resume", str(error), diagnosis_turns, total_tokens
                )
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {
                    "stage": "diagnosis",
                    "tools": skipped_tools,
                    "reason": "restored verified source artifact",
                },
            )
            return self._complete_node(
                "resume",
                {
                    "source": source,
                    "diagnosis_turns": diagnosis_turns,
                    "completion_tokens": total_tokens,
                    "next_node": "generate_patch",
                    "action": "resume",
                    "detail": "verified source restored from SQLite checkpoint",
                    "node_history": ["resume"],
                },
            )
        if phase in {PATCH_APPLIED, TARGET_PASSED}:
            integrity_error = self._verify_applied_files()
            if integrity_error is not None:
                return self._stop_node(
                    "resume", "resume", integrity_error, diagnosis_turns, total_tokens
                )
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {"tool": "apply_patch", "reason": "verified completed tool result"},
            )
            next_node = "run_regression" if phase == TARGET_PASSED else "run_target"
            return self._complete_node(
                "resume",
                {
                    "diagnosis_turns": diagnosis_turns,
                    "completion_tokens": total_tokens,
                    "next_node": next_node,
                    "action": "resume",
                    "detail": f"verified checkpoint routed to {next_node}",
                    "node_history": ["resume"],
                },
            )
        return self._stop_node(
            "resume",
            "resume",
            "checkpoint does not contain a resumable phase",
            diagnosis_turns,
            total_tokens,
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
        window = _unique_hit_window(result)
        if window is None:
            return None
        path, start_line, end_line = window
        read = self._tools.read_file(path, start_line, end_line)
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
            recovered = self._read_unique_search_result(search, issue, diagnostic_queries, trigger)
            if recovered is not None:
                return recovered
        return None

    def _persist_candidate(self, unified_diff: str) -> None:
        encoded = unified_diff.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        task = self._store.get_task(self._task_id)
        artifact_dir = Path(task.workspace) / ".tracerepair" / "candidates"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / f"{digest}.diff"
        if artifact.exists():
            if artifact.read_text(encoding="utf-8") != unified_diff:
                raise OSError("candidate artifact hash collision")
        else:
            artifact.write_text(unified_diff, encoding="utf-8", newline="\n")
        self._store.append_event(
            self._task_id,
            "candidate_patch_recorded",
            {
                "sha256": digest,
                "bytes": len(encoded),
                "artifact": artifact.relative_to(Path(task.workspace)).as_posix(),
            },
        )

    def _selector(self) -> str:
        if self._target_selector is not None:
            return self._target_selector
        return case_selector(self._store.get_task(self._task_id).case_id)

    def _latest_tool_result(self, tool: str) -> dict[str, object] | None:
        matches = [
            event.payload
            for event in self._store.list_events(self._task_id)
            if event.event_type == "tool_finished" and event.payload.get("tool") == tool
        ]
        return matches[-1] if matches else None

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

    def _verify_applied_files(self) -> str | None:
        payload = self._latest_tool_result("apply_patch")
        if payload is None or payload.get("ok") is not True:
            return "checkpoint has no successful patch application"
        summary = payload.get("summary", {})
        hashes = summary.get("file_sha256", {}) if isinstance(summary, dict) else {}
        if not isinstance(hashes, dict) or not hashes:
            return "patch checkpoint does not contain file hashes"
        workspace = Path(self._store.get_task(self._task_id).workspace).resolve()
        for relative, expected in hashes.items():
            if not isinstance(relative, str) or not is_allowed_source_path(
                relative, self._allowed_source_roots
            ):
                return "patch checkpoint contains a denied path"
            path = (workspace / relative).resolve()
            if not path.is_relative_to(workspace) or not path.is_file():
                return "patched file is unavailable during resume"
            actual = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if actual != expected:
                return "patched workspace failed integrity verification"
        return None

    def _stop_node(
        self,
        node: str,
        action: str,
        detail: str,
        diagnosis_turns: int,
        completion_tokens: int,
        *,
        transition_reason: str | None = None,
    ) -> dict[str, object]:
        if self._store.get_task(self._task_id).status is TaskStatus.RUNNING:
            self._store.transition(
                self._task_id, TaskStatus.NEEDS_HUMAN, transition_reason or detail
            )
        return self._complete_node(
            node,
            {
                "next_node": "end",
                "action": action,
                "detail": detail,
                "diagnosis_turns": diagnosis_turns,
                "completion_tokens": completion_tokens,
                "task_status": TaskStatus.NEEDS_HUMAN.value,
                "node_history": [node],
            },
        )

    def _node_started(self, node: str) -> None:
        self._store.append_event(self._task_id, "graph_node_started", {"graph_node": node})

    def _complete_node(self, node: str, update: dict[str, object]) -> dict[str, object]:
        self._store.append_event(
            self._task_id,
            "graph_node_completed",
            {
                "graph_node": node,
                "action": update.get("action"),
                "next_node": update.get("next_node"),
                "task_status": self._store.get_task(self._task_id).status.value,
            },
        )
        return update

    @staticmethod
    def _initial_evidence(issue: str, diagnostic_queries: tuple[str, ...]) -> str:
        return (
            f"Task: {issue}. Diagnose before repair. Search for distinctive source-code "
            "identifiers or literals, not the task title or case number. Choose one action only. "
            "Never guess a path: read_file paths must come from repo_map or search results. "
            "Never request patches or tests during this read-only phase. "
            f"Public entrypoint hints from the failing test: {', '.join(diagnostic_queries) or 'none'}."
        )

    @staticmethod
    def _patch_evidence(issue: str, source: FileSlice) -> str:
        return (
            f"Task: {issue}.\n"
            f"Confirmed source path: {source.path}\n"
            f"Source slice covers actual repository lines {source.start_line}-{source.end_line}. "
            "Unified-diff hunk headers must use repository line numbers, not slice-relative offsets. "
            "Return one smallest unified diff against that exact path, or handoff if the evidence is "
            "insufficient. Never edit tests. Copy context and removed lines exactly from Source; "
            "include at least three unchanged context lines around the edit. Preserve behavior outside "
            "the reported defect: inspect neighboring branches and boundary values implied by the "
            "current control flow, and make every new condition as narrow as possible.\n"
            f"Source:\n{source.content}"
        )
