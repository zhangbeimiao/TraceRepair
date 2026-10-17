"""Controlled bridge from a model suggestion to existing TraceRepair safeguards."""

from dataclasses import dataclass
from typing import Any

from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlan, ModelPlanner
from tracerepair.models import TaskStatus
from tracerepair.store import TraceStore
from tracerepair.workflow import CandidateRepairWorkflow, WorkflowStep


@dataclass(frozen=True)
class ModelWorkflowStep:
    plan: ModelPlan
    action: str
    ok: bool
    detail: str
    repair_step: WorkflowStep | None = None


class ModelGuidedWorkflow:
    """Executes only validated model suggestions through the existing tool layer."""

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        planner: ModelPlanner,
        tools: InstrumentedTools,
        repair_workflow: CandidateRepairWorkflow,
    ) -> None:
        self._task_id = task_id
        self._store = store
        self._planner = planner
        self._tools = tools
        self._repair_workflow = repair_workflow

    def step(self, evidence: str) -> ModelWorkflowStep:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.READY:
            self._store.transition(self._task_id, TaskStatus.RUNNING, "model-guided workflow started")
        task = self._store.get_task(self._task_id)
        if task.status is not TaskStatus.RUNNING:
            raise ValueError("model-guided workflow requires a runnable task")

        plan = self._planner.suggest(self._task_id, self._store, evidence)
        if plan.kind == "tool":
            result = self._execute_tool(plan)
            return ModelWorkflowStep(plan, plan.tool or "tool", result.ok, _result_detail(result))
        if plan.kind == "patch":
            # CandidateRepairWorkflow deliberately begins patch handling through
            # its human-review entry transition; model output gets no bypass.
            self._store.transition(
                self._task_id,
                TaskStatus.NEEDS_HUMAN,
                "model supplied a candidate diff requiring controlled verification",
            )
            repair_step = self._repair_workflow.submit_candidate(plan.unified_diff or "")
            return ModelWorkflowStep(
                plan,
                repair_step.action,
                repair_step.task_status is TaskStatus.AWAITING_REVIEW,
                repair_step.detail,
                repair_step,
            )

        self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, "model requested handoff")
        return ModelWorkflowStep(plan, "handoff", True, plan.reason)

    def _execute_tool(self, plan: ModelPlan) -> Any:
        arguments = plan.arguments
        if plan.tool == "repo_map":
            return self._tools.repo_map(_bounded_int(arguments.get("max_files"), 100, 1, 100))
        if plan.tool == "search_code":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip() or len(query) > 200:
                raise ValueError("model search query is invalid")
            return self._tools.search_code(query, _bounded_int(arguments.get("max_hits"), 20, 1, 50))
        if plan.tool == "read_file":
            path = arguments.get("path")
            if not isinstance(path, str) or len(path) > 300:
                raise ValueError("model read path is invalid")
            return self._tools.read_file(
                path,
                _bounded_int(arguments.get("start_line"), 1, 1, 10_000),
                _bounded_int(arguments.get("end_line"), 200, 1, 10_000),
            )
        if plan.tool == "run_tests":
            selector = arguments.get("selector")
            if not isinstance(selector, str):
                raise ValueError("model test selector is invalid")
            return self._tools.run_tests(selector)
        raise ValueError("model tool was not allowlisted")


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return min(max(value, minimum), maximum)


def _result_detail(result: object) -> str:
    error_code = getattr(result, "error_code", None)
    error = getattr(result, "error", None)
    if error_code or error:
        return str(error_code or getattr(error, "code", "tool failed"))
    return "tool completed"
