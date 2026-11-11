"""Normalize frozen TraceRepair evidence without model or repository execution."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"path escapes repository: {value}")
    return path


def _json(value: str) -> dict[str, Any]:
    path = _path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {value}")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError(f"checksum mismatch: {value}")
    return payload


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bug_id(component: dict[str, Any], run: dict[str, Any]) -> str:
    value = component.get("constant_bug_id") or run.get(component.get("bug_id_field", "case_id"))
    if not isinstance(value, str) or not value:
        raise ValueError(f"component {component['id']} has a run without a bug id")
    return f"{component.get('bug_namespace', component['id'])}:{value}"


def _diff(component: dict[str, Any], raw_bug_id: str) -> tuple[str | None, str | None]:
    value = component.get("diffs", {}).get(raw_bug_id)
    if not value:
        return None, None
    path = _path(value)
    content = path.read_text(encoding="utf-8")
    return content, hashlib.sha256(path.read_bytes()).hexdigest()


def _record(component: dict[str, Any], run: dict[str, Any], *, agent_version: str | None, index: int) -> dict[str, Any]:
    raw_id = component.get("constant_bug_id") or run.get(component.get("bug_id_field", "case_id"))
    diff, diff_sha = _diff(component, str(raw_id))
    status = str(run.get("status", "unknown"))
    return {
        "component": component["id"], "run_index": index,
        "task_id": run.get("task_id") or run.get("trace_task_id"),
        "independent_bug_id": _bug_id(component, run), "agent_version": agent_version,
        "status": status, "success": bool(run.get("success", run.get("end_to_end_success", False))),
        "needs_human": status == "needs_human", "stop_reason": run.get("stop_reason"),
        "completion_tokens": run.get("completion_tokens"), "model_calls": run.get("model_calls"),
        "tool_calls": run.get("tool_calls"), "wall_seconds": run.get("wall_seconds"),
        "target_test_passed": run.get("target_test_passed"), "regression_passed": run.get("regression_passed"),
        "diff": diff, "diff_sha256": diff_sha,
        "diff_evidence": "preserved" if diff is not None else "not_preserved_in_source_evidence",
    }


def build_report(suite_id: str, agent_version: str) -> dict[str, Any]:
    suite_path = ROOT / "evaluation" / "suites" / f"{suite_id}.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if suite.get("agent_version") != agent_version:
        raise ValueError(f"suite requires agent-version {suite.get('agent_version')!r}")
    freeze = suite.get("agent_freeze")
    if freeze:
        frozen = _json(freeze)
        frozen_version = frozen.get("agent_version") or frozen.get("release_agent_version")
        if frozen_version != agent_version:
            raise ValueError("agent freeze version mismatch")

    records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    reported_costs: list[float] = []
    for component in suite["components"]:
        path = _path(component["path"])
        payload = _json(component["path"])
        kind = component["kind"]
        if kind == "benchmark_report":
            runs = payload.get("attempts", [])
            version = payload.get("manifest", {}).get("agent_version") or payload.get("benchmark", {}).get("agent_version")
            cost = payload.get("summary", {}).get("estimated_completion_cost_cny")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                reported_costs.append(float(cost))
        elif kind == "frozen_runs":
            runs = payload.get("runs", [])
            version = (payload.get("decision", {}).get("agent_version") or payload.get("summary", {}).get("agent_version") or payload.get("metadata", {}).get("agent_version"))
        elif kind == "frozen_single_run":
            runs = [payload["run"]]
            version = payload.get("protocol", {}).get("agent_version")
        else:
            raise ValueError(f"unknown component kind: {kind}")
        if not isinstance(runs, list):
            raise ValueError(f"component {component['id']} has invalid runs")
        records.extend(_record(component, run, agent_version=version, index=i) for i, run in enumerate(runs, 1))
        task_config = component.get("task_config")
        sources.append({"component": component["id"], "path": component["path"], "sha256": _sha(path), "task_config": task_config, "task_config_sha256": _sha(_path(task_config)) if task_config else None, "availability": component.get("availability", "repository_available")})

    bugs = {record["independent_bug_id"] for record in records}
    numeric = lambda key: [record[key] for record in records if isinstance(record.get(key), (int, float)) and not isinstance(record.get(key), bool)]
    stops = Counter(str(record["stop_reason"]) for record in records if record.get("stop_reason") and not record["success"])
    summary = {
        "observed_runs": len(records), "independent_bugs": len(bugs),
        "repeated_runs": len(records) - len(bugs), "successes": sum(record["success"] for record in records),
        "needs_human": sum(record["needs_human"] for record in records),
        "observed_run_success_rate": round(sum(record["success"] for record in records) / len(records), 4) if records else None,
        "average_completion_tokens": round(mean(numeric("completion_tokens")), 2) if numeric("completion_tokens") else None,
        "average_model_calls": round(mean(numeric("model_calls")), 2) if numeric("model_calls") else None,
        "average_wall_seconds": round(mean(numeric("wall_seconds")), 3) if numeric("wall_seconds") else None,
        "estimated_cost": round(sum(reported_costs), 6) if reported_costs else None,
        "cost_scope": "source reports; completion-only where available",
        "failure_reason_distribution": dict(stops),
    }
    integrity = {"suite_manifest_sha256": _sha(suite_path), "agent_freeze_sha256": _sha(_path(freeze)) if freeze else None}
    return {"schema_version": 1, "suite_id": suite_id, "protocol": suite["protocol"], "requested_agent_version": agent_version, "description": suite["description"], "summary": summary, "records": records, "sources": sources, "integrity": integrity, "limitations": ["Evidence replay makes no provider request and does not rerun a locked task.", "Missing latency, cost, or Diff fields remain null rather than inferred.", "Observed-run success rate is not an independent-bug accuracy estimate.", "A provider model identifier is frozen, but no provider weight digest was available."]}


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [f"# TraceRepair baseline: {report['suite_id']}", "", report["description"], "", "## Summary", "", f"- Observed runs: **{s['observed_runs']}**", f"- Independent bugs: **{s['independent_bugs']}**", f"- Repeated runs: **{s['repeated_runs']}**", f"- Successful runs: **{s['successes']}**", f"- `needs_human`: **{s['needs_human']}**", f"- Average completion tokens: **{s['average_completion_tokens']}**", f"- Average model calls: **{s['average_model_calls']}**", f"- Average wall seconds: **{s['average_wall_seconds']}**", f"- Estimated cost: **{s['estimated_cost']}**", "", "## Runs", "", "| Bug | Agent | Status | Success | Tokens | Calls | Seconds | Target | Regression | Diff | Stop reason |", "|---|---|---|---:|---:|---:|---:|---|---|---|---|"]
    for r in report["records"]:
        reason = str(r.get("stop_reason") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['independent_bug_id']} | {r['agent_version']} | {r['status']} | {r['success']} | {r['completion_tokens']} | {r['model_calls']} | {r['wall_seconds']} | {r['target_test_passed']} | {r['regression_passed']} | {r['diff_evidence']} | {reason} |")
    lines.extend(["", "## Failure reasons", ""])
    if s["failure_reason_distribution"]:
        lines.extend(f"- {count} × {reason}" for reason, count in s["failure_reason_distribution"].items())
    else:
        lines.append("- None recorded")
    lines.extend(["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]])
    return "\n".join(lines) + "\n"
