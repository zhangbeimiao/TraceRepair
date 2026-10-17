"""LangGraph wrapper for TraceRepair's durable diagnostic path.

The SQLite ``TraceStore`` remains the durable source of truth.  A graph can be
rebuilt after a process restart from a task id, then routes from the completed
tool names persisted in that store.  This deliberately avoids a second,
competing persistence format before model planning is introduced.
"""

import operator
from collections.abc import Callable
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.models import TaskStatus
from tracerepair.store import TraceStore
from tracerepair.workflow import DeterministicWorkflow


class DiagnosticGraphState(TypedDict):
    """Small, JSON-safe view of one graph invocation."""

    task_id: str
    actions: Annotated[list[str], operator.add]
    detail: str
    task_status: str


class LangGraphDiagnosticWorkflow:
    """Execute the fixed diagnostic path as an inspectable LangGraph.

    It has no model node yet.  Its value at this phase is explicit routing,
    traceable graph-node completion, and safe reconstruction from ``TraceStore``.
    """

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        tools_factory: Callable[[], InstrumentedTools],
    ) -> None:
        self._task_id = task_id
        self._store = store
        self._tools_factory = tools_factory
        self._graph = self._build_graph()

    def invoke(self, *, recursion_limit: int = 12) -> DiagnosticGraphState:
        """Run or resume the graph from the durable task checkpoint."""
        if not 1 <= recursion_limit <= 30:
            raise ValueError("recursion_limit must be between 1 and 30")
        task = self._store.get_task(self._task_id)
        result = self._graph.invoke(
            {
                "task_id": self._task_id,
                "actions": [],
                "detail": "graph invoked",
                "task_status": task.status.value,
            },
            {"recursion_limit": recursion_limit},
        )
        return result

    def _build_graph(self):
        graph = StateGraph(DiagnosticGraphState)
        graph.add_node("diagnose", self._diagnose)
        graph.add_conditional_edges(START, self._route, {"diagnose": "diagnose", END: END})
        graph.add_conditional_edges("diagnose", self._route, {"diagnose": "diagnose", END: END})
        return graph.compile()

    def _route(self, _state: DiagnosticGraphState) -> str:
        task = self._store.get_task(self._task_id)
        return "diagnose" if task.status in {TaskStatus.READY, TaskStatus.RUNNING} else END

    def _diagnose(self, _state: DiagnosticGraphState) -> dict[str, object]:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.READY:
            self._store.transition(self._task_id, TaskStatus.RUNNING, "LangGraph diagnostic started")

        step = DeterministicWorkflow(
            self._task_id,
            self._store,
            self._tools_factory(),
        ).step()
        self._store.append_event(
            self._task_id,
            "graph_node_completed",
            {
                "graph_node": "diagnose",
                "action": step.action,
                "task_status": step.task_status.value,
            },
        )
        return {
            "actions": [step.action],
            "detail": step.detail,
            "task_status": step.task_status.value,
        }
