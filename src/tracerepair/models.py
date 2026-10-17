"""Stable contracts shared by the future graph, tools, API, and evaluator."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    SUCCEEDED = "succeeded"
    NEEDS_HUMAN = "needs_human"
    FAILED_SAFE = "failed_safe"
    BLOCKED_POLICY = "blocked_policy"
    INTERRUPTED = "interrupted"


TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED_SAFE,
    TaskStatus.BLOCKED_POLICY,
}


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.NEW: {TaskStatus.READY, TaskStatus.BLOCKED_POLICY},
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.NEEDS_HUMAN, TaskStatus.BLOCKED_POLICY},
    TaskStatus.RUNNING: {
        TaskStatus.AWAITING_REVIEW,
        TaskStatus.NEEDS_HUMAN,
        TaskStatus.FAILED_SAFE,
        TaskStatus.BLOCKED_POLICY,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.INTERRUPTED: {TaskStatus.READY, TaskStatus.NEEDS_HUMAN, TaskStatus.FAILED_SAFE},
    TaskStatus.AWAITING_REVIEW: {TaskStatus.SUCCEEDED, TaskStatus.NEEDS_HUMAN},
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.NEEDS_HUMAN: {TaskStatus.READY},
    TaskStatus.FAILED_SAFE: set(),
    TaskStatus.BLOCKED_POLICY: set(),
}


@dataclass(frozen=True)
class Task:
    task_id: str
    case_id: str
    issue: str
    workspace: str
    status: TaskStatus = TaskStatus.NEW


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    task_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    summary: str
    error_kind: str | None = None
    artifact_path: str | None = None


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    task_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
