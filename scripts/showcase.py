"""Replay TraceRepair's frozen public evidence without network or model calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "demo" / "dist" / "data.js"
DATA_PREFIX = "window.TRACEREPAIR_DEMO = "


def load_demo_data(path: Path = DEFAULT_DATA) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    if not source.startswith(DATA_PREFIX) or not source.endswith(";\n"):
        raise ValueError("demo data does not use the expected frozen-data wrapper")
    payload = json.loads(source[len(DATA_PREFIX) : -2])
    if not isinstance(payload, dict):
        raise ValueError("demo data must contain a JSON object")
    for key in (
        "summary",
        "historicalBenchmark",
        "traces",
        "failures",
        "recoveryScenarios",
    ):
        if key not in payload:
            raise ValueError(f"demo data is missing {key}")
    return payload


def render_showcase(
    payload: dict[str, Any],
    *,
    section: str = "all",
    case_id: str = "01",
) -> str:
    renderers = {
        "evidence": _render_evidence,
        "repair": lambda data: _render_repair(data, case_id),
        "failure": _render_failure,
        "recovery": _render_recovery,
    }
    selected = list(renderers) if section == "all" else [section]
    lines = [
        "TraceRepair Offline Showcase",
        "============================",
        "Mode: frozen evidence replay | provider requests: 0 | repository writes: 0",
    ]
    for name in selected:
        lines.extend(("", renderers[name](payload)))
    lines.extend(
        (
            "",
            "Safety boundary: the model proposes; deterministic policy and tests decide.",
            "Live demo: https://zhangbeimiao.github.io/TraceRepair/",
        )
    )
    return "\n".join(lines) + "\n"


def _render_evidence(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    historical = payload["historicalBenchmark"]
    repository = payload.get("repositoryCohort") or {}
    held_out = payload.get("lockedRepositoryResult") or {}
    locked = historical["splits"]["locked"]
    return "\n".join(
        (
            "[1] FROZEN EVIDENCE",
            "  Real historical bugs, pass@1   : "
            f"{historical['successes']}/{historical['runs']} passed; "
            f"{historical['failures']} safely rejected",
            "  Safety outcome                  : "
            f"{historical['incorrectAcceptedPatches']} incorrect patches accepted; "
            f"{historical['humanHandoffs']} human handoffs",
            "  Locked protocol                 : "
            f"{locked['successes']}/{locked['attempts']} passed; each task ran once; "
            "no post-hoc retry",
            "  Safe-stop evidence              : two policy-valid candidates failed their "
            "target tests and were not accepted",
            f"  EventRelay controlled regression: {summary['successes']}/{summary['runs']} passed",
            "  Public configured repository    : "
            f"{repository.get('successes', '-')}/{repository.get('runs', '-')} passed, "
            f"avg tokens={repository.get('averageTokens', '-')}, "
            f"avg tools={repository.get('averageToolCalls', '-')}",
            "  Held-out repository, one shot   : "
            f"{'1/1 passed' if held_out.get('success') else '0/1 safely stopped'}, "
            f"tokens={held_out.get('tokens', '-')}, calls={held_out.get('modelCalls', '-')}, "
            f"tools={held_out.get('toolCalls', '-')}, "
            f"retried={str(held_out.get('retried', '-')).lower()}",
            "  Claim boundary                   : five real historical bugs validate the bounded "
            "workflow; they do not establish broad repair accuracy",
            "  Versioning rule                  : any patch-location policy change requires a new "
            "agent version and a new frozen benchmark",
        )
    )


def _render_repair(payload: dict[str, Any], case_id: str) -> str:
    trace = next(
        (item for item in payload["traces"] if str(item.get("caseId")) == case_id),
        None,
    )
    if trace is None:
        available = ", ".join(str(item.get("caseId")) for item in payload["traces"])
        raise ValueError(f"unknown case {case_id}; available cases: {available}")
    tools = _ordered_tools(trace["timeline"])
    patch = trace["patchPreview"]
    lines = [
        f"[2] CONTROLLED EVENTRELAY REPAIR TRACE - case {trace['caseId']} ({trace['caseName']})",
        "  Evidence scope: engineering regression; not part of the 3/5 historical benchmark",
        f"  Issue       : {trace['issue']}",
        f"  Model usage : calls={trace['modelCalls']}, output_tokens={trace['tokens']}",
        f"  Tool chain  : {' -> '.join(tools)}",
        f"  Patch       : {patch['file']} (+{patch['addedLines']}/-{patch['removedLines']})",
        "  Diff:",
    ]
    lines.extend(f"    {line['text']}" for line in patch["lines"])
    lines.append("  Verification gates:")
    for gate in ("policy", "apply", "target", "regression"):
        result = trace["verification"][gate]
        duration = "" if result.get("durationMs") is None else f" ({result['durationMs']} ms)"
        lines.append(
            f"    [{'PASS' if result['ok'] else 'STOP'}] {gate:<10} {result['detail']}{duration}"
        )
    lines.append(f"  Final state : {trace['status']} (human review still required)")
    return "\n".join(lines)


def _render_failure(payload: dict[str, Any]) -> str:
    failure = payload["failures"][0]
    control = failure["control"]
    return "\n".join(
        (
            f"[3] CONTROLLED EVENTRELAY SAFE FAILURE - {failure['category']}",
            "  Evidence scope: retained engineering failure; not part of the 3/5 benchmark",
            f"  Issue         : {failure['issue']}",
            f"  Error         : {control['errorCode']}",
            f"  Patch applied : {str(control['patchApplied']).lower()}",
            f"  Tests started : {str(control['testsStarted']).lower()}",
            f"  Final state   : {failure['status']}",
            f"  Stop reason   : {control['stopReason']}",
            "  Outcome       : unsafe candidate contained; repository was not modified",
        )
    )


def _render_recovery(payload: dict[str, Any]) -> str:
    recovery = next(
        item
        for item in payload["recoveryScenarios"]
        if item.get("crash_point") == "patch_applied"
    )
    phase_one_tools = list(recovery["phase_one_tools"])
    final_tools = list(recovery["final_tools"])
    resumed_tools = (
        final_tools[len(phase_one_tools) :]
        if final_tools[: len(phase_one_tools)] == phase_one_tools
        else final_tools
    )
    return "\n".join(
        (
            "[4] CONTROLLED CHECKPOINT CRASH RECOVERY - patch already applied",
            "  Evidence scope: deterministic recovery test; not a benchmark repair attempt",
            f"  Before crash : {' -> '.join(phase_one_tools)}",
            "  Crash        : process exits after checkpoint persistence",
            f"  Resume       : model_calls={recovery['resume_model_calls']}, "
            f"skipped={','.join(recovery['skipped_tools'])}",
            f"  After resume : {' -> '.join(resumed_tools)}",
            f"  Final state  : {recovery['final_status']}",
            "  Guarantee    : completed tools and patch application are not repeated",
        )
    )


def _ordered_tools(timeline: list[str]) -> list[str]:
    tools: list[str] = []
    for event in timeline:
        if not event.startswith("tool "):
            continue
        tool = event.split(" ", 2)[1]
        if tool not in tools:
            tools.append(tool)
    return tools


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        choices=("all", "evidence", "repair", "failure", "recovery"),
        default="all",
    )
    parser.add_argument("--case", default="01", help="frozen EventRelay case for repair replay")
    arguments = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        print(
            render_showcase(
                load_demo_data(),
                section=arguments.section,
                case_id=arguments.case,
            ),
            end="",
        )
    except (OSError, ValueError, KeyError, StopIteration) as error:
        raise SystemExit(f"Offline showcase failed safely: {error}") from error


if __name__ == "__main__":
    main()
