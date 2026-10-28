"""Tamper-evident, pass@1 benchmark manifests and result ledgers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from tracerepair.repository_task import RepositoryTaskSpec


SCHEMA_VERSION = 1
_BENCHMARK_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,63}$")
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IGNORED_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}


class BenchmarkManifestError(ValueError):
    """A fail-closed benchmark definition or ledger error."""


@dataclass(frozen=True)
class HistoricalSource:
    repository_url: str
    buggy_commit: str
    fixed_commit: str
    issue_url: str | None = None


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    split: str
    config_path: Path
    config_sha256: str
    repository_sha256: str
    source: HistoricalSource


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str
    chunker_version: str
    embedding_model: str | None
    embedding_dimensions: int | None
    top_k: int
    rrf_k: int


@dataclass(frozen=True)
class FrozenContracts:
    agent_config_sha256: str
    prompt_protocol_sha256: str
    prompt_security_sha256: str
    retrieval_gate_sha256: str


@dataclass(frozen=True)
class BenchmarkManifest:
    benchmark_id: str
    agent_version: str
    model: str
    protocol: str
    completion_cny_per_million_tokens: float
    manifest_path: Path
    manifest_sha256: str
    tasks: tuple[BenchmarkTask, ...]
    retrieval: RetrievalConfig | None = None
    contracts: FrozenContracts | None = None

    @classmethod
    def load(cls, path: Path) -> "BenchmarkManifest":
        manifest_path = path.resolve()
        if not manifest_path.is_file():
            raise BenchmarkManifestError(f"benchmark manifest does not exist: {path}")
        try:
            raw = manifest_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BenchmarkManifestError("benchmark manifest is not valid UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise BenchmarkManifestError("benchmark manifest root must be an object")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise BenchmarkManifestError("unsupported benchmark schema_version")
        benchmark_id = _text(payload, "benchmark_id", 64)
        if not _BENCHMARK_ID.fullmatch(benchmark_id):
            raise BenchmarkManifestError("benchmark_id must be a lowercase stable identifier")
        agent_version = _text(payload, "agent_version", 64)
        model = _text(payload, "model", 100)
        protocol = _text(payload, "protocol", 40)
        if protocol != "pass@1":
            raise BenchmarkManifestError("only the pass@1 protocol is supported")
        price = payload.get("completion_cny_per_million_tokens", 0.0)
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(float(price))
            or price < 0
        ):
            raise BenchmarkManifestError(
                "completion_cny_per_million_tokens must be a non-negative number"
            )
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list) or not 2 <= len(raw_tasks) <= 50:
            raise BenchmarkManifestError("tasks must contain between 2 and 50 entries")
        tasks: list[BenchmarkTask] = []
        seen_ids: set[str] = set()
        seen_configs: set[Path] = set()
        for item in raw_tasks:
            task = _load_task(item, manifest_path.parent)
            if task.task_id in seen_ids:
                raise BenchmarkManifestError(f"duplicate benchmark task_id: {task.task_id}")
            if task.config_path in seen_configs:
                raise BenchmarkManifestError(
                    f"task config reused by multiple pass@1 tasks: {task.config_path.name}"
                )
            seen_ids.add(task.task_id)
            seen_configs.add(task.config_path)
            tasks.append(task)
        retrieval = _load_retrieval(payload.get("retrieval"))
        contracts = _load_contracts(payload.get("contracts"))
        return cls(
            benchmark_id=benchmark_id,
            agent_version=agent_version,
            model=model,
            protocol=protocol,
            completion_cny_per_million_tokens=float(price),
            manifest_path=manifest_path,
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            tasks=tuple(tasks),
            retrieval=retrieval,
            contracts=contracts,
        )

    def lock_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "benchmark_id": self.benchmark_id,
            "protocol": self.protocol,
            "agent_version": self.agent_version,
            "model": self.model,
            "manifest_sha256": self.manifest_sha256,
            "completion_cny_per_million_tokens": self.completion_cny_per_million_tokens,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "split": task.split,
                    "task_config": task.config_path.name,
                    "task_config_sha256": task.config_sha256,
                    "repository_sha256": task.repository_sha256,
                    "source": asdict(task.source),
                }
                for task in self.tasks
            ],
        }
        if self.retrieval is not None:
            payload["retrieval"] = asdict(self.retrieval)
        if self.contracts is not None:
            payload["contracts"] = asdict(self.contracts)
        return payload


def append_ledger_record(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    """Append one hash-chained JSON record after verifying the existing chain."""

    records = read_ledger(path)
    record: dict[str, object] = {
        "sequence": len(records) + 1,
        "previous_record_sha256": records[-1]["record_sha256"] if records else None,
        "recorded_at": datetime.now(UTC).isoformat(),
        **dict(payload),
    }
    record["record_sha256"] = _payload_sha256(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
    return record


def read_ledger(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    previous: str | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise BenchmarkManifestError("benchmark ledger is unreadable") from error
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            raise BenchmarkManifestError(f"benchmark ledger contains a blank line at {index}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkManifestError(f"benchmark ledger line {index} is invalid JSON") from error
        if not isinstance(record, dict):
            raise BenchmarkManifestError(f"benchmark ledger line {index} is not an object")
        actual_hash = record.get("record_sha256")
        unsigned = dict(record)
        unsigned.pop("record_sha256", None)
        if record.get("sequence") != index:
            raise BenchmarkManifestError(f"benchmark ledger sequence mismatch at line {index}")
        if record.get("previous_record_sha256") != previous:
            raise BenchmarkManifestError(f"benchmark ledger chain mismatch at line {index}")
        if actual_hash != _payload_sha256(unsigned):
            raise BenchmarkManifestError(f"benchmark ledger content mismatch at line {index}")
        previous = str(actual_hash)
        records.append(record)
    return records


def build_report(
    manifest: BenchmarkManifest, records: list[dict[str, object]]
) -> dict[str, object]:
    matching_records = [
        record
        for record in records
        if record.get("benchmark_id") == manifest.benchmark_id
        and record.get("manifest_sha256") == manifest.manifest_sha256
    ]
    attempts = _collapse_attempt_records(matching_records)
    successes = sum(record.get("success") is True for record in attempts)
    failures = len(attempts) - successes
    durations = sorted(float(record.get("wall_seconds", 0.0)) for record in attempts)
    completion_tokens = sum(int(record.get("completion_tokens", 0)) for record in attempts)
    attempted_ids = {str(record.get("benchmark_task_id")) for record in attempts}
    expected_ids = {task.task_id for task in manifest.tasks}
    lower, upper = _wilson_interval(successes, len(attempts))
    terminal_hash = matching_records[-1].get("record_sha256") if matching_records else None
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "benchmark": manifest.lock_payload(),
        "integrity": {
            "ledger_records_verified": len(records),
            "terminal_record_sha256": terminal_hash,
            "claim": "tamper-evident after the terminal hash is published; not an immutable store",
        },
        "summary": {
            "expected_tasks": len(manifest.tasks),
            "attempted_tasks": len(attempts),
            "missing_task_ids": sorted(expected_ids - attempted_ids),
            "successes": successes,
            "failures": failures,
            "pass_at_1": round(successes / len(attempts), 4) if attempts else 0.0,
            "wilson_95_percent": {"lower": lower, "upper": upper},
            "human_handoffs": sum(
                record.get("status") == "needs_human" for record in attempts
            ),
            "incorrect_accepted_patches": sum(
                record.get("status") in {"awaiting_review", "succeeded"}
                and record.get("regression_passed") is not True
                for record in attempts
            ),
            "average_completion_tokens": round(completion_tokens / len(attempts), 2)
            if attempts
            else 0.0,
            "total_completion_tokens": completion_tokens,
            "estimated_completion_cost_cny": round(
                completion_tokens
                * manifest.completion_cny_per_million_tokens
                / 1_000_000,
                6,
            )
            if manifest.completion_cny_per_million_tokens > 0
            else None,
            "cost_scope": (
                "completion tokens only; prompt-token cost is not recorded by v0.7"
                if manifest.completion_cny_per_million_tokens > 0
                else "unavailable: no completion-token price was frozen in the manifest"
            ),
            "p50_wall_seconds": _percentile(durations, 0.50),
            "p95_wall_seconds": _percentile(durations, 0.95),
        },
        "attempts": attempts,
    }
    report["report_sha256"] = _payload_sha256(report)
    return report


def _collapse_attempt_records(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    attempts: dict[str, dict[str, object]] = {}
    finished: set[str] = set()
    for record in records:
        task_id = str(record.get("benchmark_task_id", ""))
        if not task_id:
            raise BenchmarkManifestError("benchmark ledger record is missing benchmark_task_id")
        kind = str(record.get("record_kind", "attempt_finished"))
        if kind == "attempt_started":
            if task_id in attempts:
                raise BenchmarkManifestError(f"duplicate pass@1 attempt start: {task_id}")
            attempts[task_id] = {
                **record,
                "status": "interrupted_before_result_record",
                "success": False,
                "model_calls": 0,
                "completion_tokens": 0,
                "tool_calls": 0,
                "tool_failures": 0,
                "target_test_passed": False,
                "regression_passed": False,
                "wall_seconds": 0.0,
                "stop_reason": "attempt started but no durable result record exists",
            }
        elif kind == "attempt_finished":
            if task_id in finished:
                raise BenchmarkManifestError(f"duplicate pass@1 attempt result: {task_id}")
            attempts[task_id] = record
            finished.add(task_id)
        else:
            raise BenchmarkManifestError(f"unknown benchmark ledger record kind: {kind}")
    return list(attempts.values())


def write_report(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="ascii", newline="\n"
    )


def _load_task(payload: object, base_directory: Path) -> BenchmarkTask:
    if not isinstance(payload, dict):
        raise BenchmarkManifestError("each benchmark task must be an object")
    task_id = _text(payload, "id", 64)
    if not _TASK_ID.fullmatch(task_id):
        raise BenchmarkManifestError("task id must be lowercase and hyphenated")
    split = _text(payload, "split", 20)
    if split not in {"development", "locked"}:
        raise BenchmarkManifestError("task split must be development or locked")
    raw_config = _text(payload, "task_config", 500)
    config_path = (base_directory / raw_config).resolve()
    if not config_path.is_file():
        raise BenchmarkManifestError(f"task config does not exist: {raw_config}")
    spec = RepositoryTaskSpec.load(config_path)
    source_payload = payload.get("source")
    if not isinstance(source_payload, dict):
        raise BenchmarkManifestError("task source must be an object")
    repository_url = _text(source_payload, "repository_url", 500)
    if not repository_url.startswith("https://github.com/"):
        raise BenchmarkManifestError("source repository_url must be an HTTPS GitHub URL")
    buggy_commit = _text(source_payload, "buggy_commit", 40)
    fixed_commit = _text(source_payload, "fixed_commit", 40)
    if not _COMMIT.fullmatch(buggy_commit) or not _COMMIT.fullmatch(fixed_commit):
        raise BenchmarkManifestError("source commits must be full lowercase SHA-1 values")
    issue_url = source_payload.get("issue_url")
    if issue_url is not None and (
        not isinstance(issue_url, str) or not issue_url.startswith("https://github.com/")
    ):
        raise BenchmarkManifestError("source issue_url must be an HTTPS GitHub URL")
    config_bytes = config_path.read_bytes()
    return BenchmarkTask(
        task_id=task_id,
        split=split,
        config_path=config_path,
        config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        repository_sha256=_repository_sha256(spec.repository_root),
        source=HistoricalSource(
            repository_url=repository_url,
            buggy_commit=buggy_commit,
            fixed_commit=fixed_commit,
            issue_url=issue_url,
        ),
    )


def _load_retrieval(payload: object) -> RetrievalConfig | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise BenchmarkManifestError("retrieval must be an object")
    expected = {
        "mode",
        "chunker_version",
        "embedding_model",
        "embedding_dimensions",
        "top_k",
        "rrf_k",
    }
    if set(payload) != expected:
        raise BenchmarkManifestError("retrieval fields must be explicitly frozen")
    mode = _text(payload, "mode", 20)
    if mode not in {"fts5", "hybrid"}:
        raise BenchmarkManifestError("retrieval mode must be fts5 or hybrid")
    chunker = _text(payload, "chunker_version", 60)
    model = payload.get("embedding_model")
    dimensions = payload.get("embedding_dimensions")
    if mode == "fts5":
        if model is not None or dimensions is not None:
            raise BenchmarkManifestError("fts5 retrieval cannot declare an embedding model")
    else:
        if not isinstance(model, str) or not model.strip() or len(model) > 100:
            raise BenchmarkManifestError("hybrid retrieval must freeze an embedding model")
        if dimensions not in {256, 512, 768, 1024}:
            raise BenchmarkManifestError("hybrid retrieval has unsupported dimensions")
        model = model.strip()
    top_k = payload.get("top_k")
    rrf_k = payload.get("rrf_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 10:
        raise BenchmarkManifestError("retrieval top_k must be between 1 and 10")
    if not isinstance(rrf_k, int) or isinstance(rrf_k, bool) or not 1 <= rrf_k <= 1000:
        raise BenchmarkManifestError("retrieval rrf_k must be between 1 and 1000")
    return RetrievalConfig(
        mode=mode,
        chunker_version=chunker,
        embedding_model=model,
        embedding_dimensions=dimensions,
        top_k=top_k,
        rrf_k=rrf_k,
    )


def _load_contracts(payload: object) -> FrozenContracts | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise BenchmarkManifestError("contracts must be an object")
    expected = {
        "agent_config_sha256",
        "prompt_protocol_sha256",
        "prompt_security_sha256",
        "retrieval_gate_sha256",
    }
    if set(payload) != expected:
        raise BenchmarkManifestError("contract hashes must be explicitly frozen")
    values: dict[str, str] = {}
    for key in sorted(expected):
        value = _text(payload, key, 64)
        if not _SHA256.fullmatch(value):
            raise BenchmarkManifestError(f"{key} must be a lowercase SHA-256")
        values[key] = value
    return FrozenContracts(**values)


def _repository_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in _IGNORED_PARTS for part in path.relative_to(root).parts)
    ]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _payload_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _text(payload: Mapping[str, Any], key: str, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BenchmarkManifestError(f"{key} must be a non-empty string up to {maximum} chars")
    return value.strip()


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    rank = max(1, math.ceil(fraction * len(values)))
    return round(values[rank - 1], 3)


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)
