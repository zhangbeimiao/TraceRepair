"""Native function-calling planner with deterministic host-side enforcement."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from tracerepair.model_planner import (
    BudgetExceeded,
    ModelPlan,
    PlannerConfig,
    PlannerError,
    PlannerTransport,
    _normalize_unified_diff,
)
from tracerepair.prompt_registry import get_prompt
from tracerepair.store import TraceStore


READ_ONLY_FUNCTIONS = {"repo_map", "search_code", "read_file"}
CONTROL_FUNCTIONS = {"propose_patch", "handoff"}
FUNCTION_ALIASES = {"apply_patch": "propose_patch"}


def _function(name: str, description: str, properties: dict[str, object], required: list[str]):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


FUNCTION_SCHEMAS: dict[str, dict[str, object]] = {
    "repo_map": _function(
        "repo_map",
        "List a bounded map of allowlisted Python source files.",
        {"max_files": {"type": "integer", "minimum": 1, "maximum": 100}},
        ["max_files"],
    ),
    "search_code": _function(
        "search_code",
        "Search allowlisted Python source using one literal substring, never regex.",
        {
            "query": {"type": "string", "minLength": 2, "maxLength": 200},
            "max_hits": {"type": "integer", "minimum": 1, "maximum": 30},
        },
        ["query", "max_hits"],
    ),
    "read_file": _function(
        "read_file",
        "Read a bounded line range from one exact path observed in a prior tool result.",
        {
            "path": {"type": "string", "minLength": 1, "maxLength": 300},
            "start_line": {"type": "integer", "minimum": 1, "maximum": 10000},
            "end_line": {"type": "integer", "minimum": 1, "maximum": 10000},
        },
        ["path", "start_line", "end_line"],
    ),
    "propose_patch": _function(
        "propose_patch",
        "Propose one complete unified diff. This does not apply or approve the patch.",
        {
            "unified_diff": {"type": "string", "minLength": 1, "maxLength": 12000},
            "reason": {"type": "string", "maxLength": 500},
        },
        ["unified_diff"],
    ),
    "handoff": _function(
        "handoff",
        "Stop safely and request a human when evidence is insufficient.",
        {"reason": {"type": "string", "maxLength": 500}},
        [],
    ),
}


class NativeFunctionPlanner:
    """Request exactly one native tool call and persist its immutable metadata."""

    def __init__(self, transport: PlannerTransport, config: PlannerConfig | None = None) -> None:
        self._transport = transport
        self._config = config or PlannerConfig()

    def suggest(
        self,
        task_id: str,
        store: TraceStore,
        evidence: str,
        *,
        allowed_tools: set[str] | None = None,
        allow_patch: bool = True,
        stage: str | None = None,
    ) -> ModelPlan:
        checkpoint = store.load_checkpoint(task_id)
        budget = dict(checkpoint.get("model_budget", {}))
        calls = int(budget.get("calls", 0))
        used_tokens = int(budget.get("completion_tokens", 0))
        if calls >= self._config.max_calls_per_task:
            raise BudgetExceeded("model call budget exhausted")
        if used_tokens + self._config.max_completion_tokens > self._config.max_total_completion_tokens:
            raise BudgetExceeded("model token budget exhausted")

        permitted = READ_ONLY_FUNCTIONS if allowed_tools is None else set(allowed_tools)
        if not permitted <= READ_ONLY_FUNCTIONS:
            raise ValueError("allowed_tools must be a subset of the read-only function allowlist")
        resolved_stage = stage or ("patch_generation" if allow_patch and not permitted else "diagnosis")
        prompt = get_prompt(resolved_stage)
        advertised = sorted(permitted) if not allow_patch else ["propose_patch"]
        advertised.append("handoff")
        tools = [FUNCTION_SCHEMAS[name] for name in advertised]
        schema_sha256 = _canonical_sha256(tools)
        payload: dict[str, object] = {
            "model": self._config.model,
            "temperature": 0,
            "max_tokens": self._config.max_completion_tokens,
            "enable_thinking": False,
            "parallel_tool_calls": False,
            "tool_choice": "required",
            "tools": tools,
            "messages": prompt.messages(
                evidence, max_context_chars=self._config.max_context_chars
            ),
        }
        response = self._transport.complete(payload)
        completion_tokens = _reported_completion_tokens(response)
        try:
            plan, call_meta = self._parse_response(
                response,
                permitted=permitted,
                allow_patch=allow_patch,
            )
            if completion_tokens > self._config.max_completion_tokens:
                raise PlannerError("model response exceeded completion token limit")
        except PlannerError as error:
            self._record(
                task_id,
                store,
                checkpoint,
                calls,
                used_tokens,
                completion_tokens,
                prompt_id=prompt.prompt_id,
                prompt_sha256=prompt.sha256,
                schema_sha256=schema_sha256,
                stage=resolved_stage,
                kind="invalid",
                function_name=None,
                provider_function_name=_response_function_name(response),
                compatibility_normalized=False,
                arguments_sha256=None,
                tool_call_id_sha256=None,
                policy_accepted=False,
                parse_error=str(error),
                response_sha256=_canonical_sha256(response),
                prompt_chars=len(evidence[: self._config.max_context_chars]),
            )
            raise
        self._record(
            task_id,
            store,
            checkpoint,
            calls,
            used_tokens,
            plan.completion_tokens,
            prompt_id=prompt.prompt_id,
            prompt_sha256=prompt.sha256,
            schema_sha256=schema_sha256,
            stage=resolved_stage,
            kind=plan.kind,
            function_name=str(call_meta["name"]),
            provider_function_name=str(call_meta["provider_name"]),
            compatibility_normalized=call_meta["compatibility_normalized"] == "true",
            arguments_sha256=str(call_meta["arguments_sha256"]),
            tool_call_id_sha256=str(call_meta["tool_call_id_sha256"]),
            policy_accepted=True,
            parse_error=None,
            response_sha256=None,
            prompt_chars=len(evidence[: self._config.max_context_chars]),
        )
        return plan

    def _parse_response(
        self,
        response: Mapping[str, object],
        *,
        permitted: set[str],
        allow_patch: bool,
    ) -> tuple[ModelPlan, dict[str, str]]:
        try:
            choices = response["choices"]
            first = choices[0]  # type: ignore[index]
            message = first["message"]  # type: ignore[index]
            calls = message["tool_calls"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as error:
            raise PlannerError("model returned no native function call") from error
        if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], Mapping):
            raise PlannerError("model must return exactly one native function call")
        call = calls[0]
        function = call.get("function")
        if call.get("type", "function") != "function" or not isinstance(function, Mapping):
            raise PlannerError("model returned an invalid function-call envelope")
        provider_name = function.get("name")
        if not isinstance(provider_name, str):
            raise PlannerError("model proposed an unknown function")
        name = FUNCTION_ALIASES.get(provider_name, provider_name)
        if name not in FUNCTION_SCHEMAS:
            raise PlannerError("model proposed an unknown function")
        raw_arguments = function.get("arguments", "{}")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise PlannerError("model returned invalid function arguments") from error
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise PlannerError("model function arguments must be an object")
        arguments = _normalize_compatibility_arguments(provider_name, name, arguments)
        _validate_arguments(name, arguments)
        if name in READ_ONLY_FUNCTIONS and name not in permitted:
            raise PlannerError("model proposed a function outside the current stage")
        if name == "propose_patch" and not allow_patch:
            raise PlannerError("model proposed a patch outside the patch stage")
        if name in permitted and allow_patch:
            raise PlannerError("read-only functions are not allowed in the patch stage")

        reason = _safe_reason(arguments.get("reason"), fallback=f"model selected {name}")
        completion_tokens = _reported_completion_tokens(response)
        if name == "handoff":
            plan = ModelPlan("handoff", None, {}, None, reason, completion_tokens)
        elif name == "propose_patch":
            diff = _normalize_unified_diff(str(arguments["unified_diff"]))
            if diff is None:
                raise PlannerError("model patch has invalid unified diff headers")
            plan = ModelPlan("patch", None, {}, diff, reason, completion_tokens)
        else:
            plan = ModelPlan("tool", name, arguments, None, reason, completion_tokens)
        call_id = str(call.get("id", "missing"))
        return plan, {
            "name": name,
            "provider_name": provider_name,
            "compatibility_normalized": str(provider_name != name).lower(),
            "arguments_sha256": _canonical_sha256(arguments),
            "tool_call_id_sha256": hashlib.sha256(call_id.encode("utf-8")).hexdigest(),
        }

    def _record(
        self,
        task_id: str,
        store: TraceStore,
        checkpoint: dict[str, Any],
        calls: int,
        used_tokens: int,
        completion_tokens: int,
        *,
        prompt_id: str,
        prompt_sha256: str,
        schema_sha256: str,
        stage: str,
        kind: str,
        function_name: str | None,
        provider_function_name: str | None,
        compatibility_normalized: bool,
        arguments_sha256: str | None,
        tool_call_id_sha256: str | None,
        policy_accepted: bool,
        parse_error: str | None,
        response_sha256: str | None,
        prompt_chars: int,
    ) -> None:
        checkpoint["model_budget"] = {
            "calls": calls + 1,
            "completion_tokens": used_tokens + completion_tokens,
            "max_calls": self._config.max_calls_per_task,
            "max_completion_tokens": self._config.max_total_completion_tokens,
        }
        checkpoint["prompt_contract"] = {
            "prompt_id": prompt_id,
            "prompt_sha256": prompt_sha256,
            "tool_schema_sha256": schema_sha256,
            "native_function_calling": True,
        }
        store.save_checkpoint(task_id, checkpoint)
        payload: dict[str, object] = {
            "kind": kind,
            "tool": function_name if function_name in READ_ONLY_FUNCTIONS else None,
            "function_name": function_name,
            "provider_function_name": provider_function_name,
            "compatibility_normalized": compatibility_normalized,
            "completion_tokens": completion_tokens,
            "prompt_chars": prompt_chars,
            "prompt_id": prompt_id,
            "prompt_sha256": prompt_sha256,
            "tool_schema_sha256": schema_sha256,
            "arguments_sha256": arguments_sha256,
            "tool_call_id_sha256": tool_call_id_sha256,
            "stage": stage,
            "native_function_calling": True,
            "policy_accepted": policy_accepted,
        }
        if parse_error is not None:
            payload["parse_error"] = parse_error
        if response_sha256 is not None:
            payload["response_sha256"] = response_sha256
        store.append_event(task_id, "model_plan_recorded", payload)


def _validate_arguments(name: str, arguments: dict[str, object]) -> None:
    function = FUNCTION_SCHEMAS[name]["function"]
    parameters = function["parameters"]  # type: ignore[index]
    allowed = set(parameters["properties"])  # type: ignore[index]
    required = set(parameters["required"])  # type: ignore[index]
    if set(arguments) - allowed:
        raise PlannerError("model returned unknown function arguments")
    if required - set(arguments):
        raise PlannerError("model omitted required function arguments")
    if name == "repo_map":
        _bounded_integer(arguments.get("max_files"), 1, 100, "max_files")
    elif name == "search_code":
        query = arguments.get("query")
        if not isinstance(query, str) or not 2 <= len(query) <= 200:
            raise PlannerError("model returned an invalid literal search query")
        if any(token in query for token in ("|", "*", "(?", "[", "]", "\\d", "\\s")):
            raise PlannerError("model search query must be a plain literal")
        _bounded_integer(arguments.get("max_hits"), 1, 30, "max_hits")
    elif name == "read_file":
        path = arguments.get("path")
        if not isinstance(path, str) or len(path) > 300:
            raise PlannerError("model returned an invalid read path")
        parsed = PurePosixPath(path.replace("\\", "/"))
        if parsed.is_absolute() or ".." in parsed.parts or parsed.suffix != ".py":
            raise PlannerError("model returned an unsafe read path")
        start = _bounded_integer(arguments.get("start_line"), 1, 10_000, "start_line")
        end = _bounded_integer(arguments.get("end_line"), 1, 10_000, "end_line")
        if end < start or end - start > 400:
            raise PlannerError("model returned an invalid read range")
    elif name == "propose_patch":
        value = arguments.get("unified_diff")
        if not isinstance(value, str) or not 1 <= len(value) <= 12_000:
            raise PlannerError("model patch is not a bounded string")
    if "reason" in arguments:
        reason = arguments["reason"]
        if isinstance(reason, str) and len(reason) > 4_000:
            raise PlannerError("model reason is invalid")


def _normalize_compatibility_arguments(
    provider_name: str,
    canonical_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    """Normalize one proposal-only alias without expanding execution authority."""

    normalized = dict(arguments)
    if provider_name == "apply_patch" and canonical_name == "propose_patch":
        alternatives = [key for key in ("patch", "diff") if key in normalized]
        if "unified_diff" not in normalized and len(alternatives) == 1:
            normalized["unified_diff"] = normalized.pop(alternatives[0])
    return normalized


def _response_function_name(response: Mapping[str, object]) -> str | None:
    """Return a bounded identifier for diagnostics without persisting arguments."""

    try:
        calls = response["choices"][0]["message"]["tool_calls"]  # type: ignore[index]
        name = calls[0]["function"]["name"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(name, str) or len(name) > 80:
        return None
    return name if name.replace("_", "").isalnum() else None


def _bounded_integer(value: object, minimum: int, maximum: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise PlannerError(f"model returned an invalid {name}")
    return value


def _safe_reason(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    compact = " ".join(value.split())
    return compact[:500] or fallback


def _reported_completion_tokens(response: Mapping[str, object]) -> int:
    usage = response.get("usage", {})
    if not isinstance(usage, Mapping):
        return 0
    try:
        return max(0, int(usage.get("completion_tokens", 0)))
    except (TypeError, ValueError):
        return 0


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
