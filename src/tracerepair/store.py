"""Small SQLite persistence layer for task checkpoints and auditable traces."""

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracerepair.models import ALLOWED_TRANSITIONS, Task, TaskStatus, TraceEvent


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TraceStore:
    """Persists only JSON-serialisable task state; large artifacts stay on disk."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    status TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trace_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS trace_events_task_sequence
                    ON trace_events(task_id, sequence);
                """
            )

    def create_task(self, task: Task) -> None:
        if task.status is not TaskStatus.NEW:
            raise ValueError("newly persisted tasks must begin in 'new' status")
        now = _now()
        try:
            with self._connection:
                self._connection.execute(
                    """INSERT INTO tasks
                    (task_id, case_id, issue, workspace, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (task.task_id, task.case_id, task.issue, task.workspace, task.status, now, now),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"task already exists: {task.task_id}") from error
        self.append_event(task.task_id, "task_created", {"case_id": task.case_id})

    def get_task(self, task_id: str) -> Task:
        row = self._connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        return Task(
            task_id=row["task_id"],
            case_id=row["case_id"],
            issue=row["issue"],
            workspace=row["workspace"],
            status=TaskStatus(row["status"]),
        )

    def transition(self, task_id: str, target: TaskStatus, reason: str) -> Task:
        task = self.get_task(task_id)
        if target not in ALLOWED_TRANSITIONS[task.status]:
            raise ValueError(f"invalid transition: {task.status} -> {target}")
        with self._connection:
            self._connection.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (target, _now(), task_id),
            )
        self.append_event(
            task_id,
            "status_changed",
            {"from": task.status, "to": target, "reason": reason},
        )
        return self.get_task(task_id)

    def save_checkpoint(self, task_id: str, state: Mapping[str, Any]) -> None:
        self.get_task(task_id)
        encoded = json.dumps(dict(state), ensure_ascii=False, sort_keys=True)
        with self._connection:
            self._connection.execute(
                "UPDATE tasks SET checkpoint_json = ?, updated_at = ? WHERE task_id = ?",
                (encoded, _now(), task_id),
            )
        self.append_event(task_id, "checkpoint_saved", {"keys": sorted(state)})

    def load_checkpoint(self, task_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT checkpoint_json FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        return json.loads(row["checkpoint_json"])

    def append_event(self, task_id: str, event_type: str, payload: Mapping[str, Any]) -> TraceEvent:
        self.get_task(task_id)
        now = _now()
        with self._connection:
            cursor = self._connection.execute(
                """INSERT INTO trace_events (task_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)""",
                (task_id, event_type, json.dumps(dict(payload), ensure_ascii=False), now),
            )
        return TraceEvent(cursor.lastrowid, task_id, event_type, dict(payload), now)

    def list_events(self, task_id: str) -> list[TraceEvent]:
        self.get_task(task_id)
        rows = self._connection.execute(
            "SELECT * FROM trace_events WHERE task_id = ? ORDER BY sequence", (task_id,)
        ).fetchall()
        return [
            TraceEvent(
                sequence=row["sequence"],
                task_id=row["task_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
