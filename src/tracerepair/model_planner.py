"""Low-budget, JSON-only Model Studio planner for the future repair agent.

The planner may suggest an allowlisted next tool or a candidate diff.  It never
executes either: existing tool contracts, patch policy, tests, and review remain
the enforcement points.
"""

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tracerepair.store import TraceStore


_ALLOWED_TOOLS = {"repo_map", "search_code", "read_file", "run_tests"}


class PlannerError(RuntimeError):
    """A safe failure which should send control back to a human or graph guard."""


class BudgetExceeded(PlannerError):
    pass


class PlannerTransport(Protocol):
    def complete(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class PlannerConfig:
    # qwen3.8-flash is available in the configured workspace and supports the
    # OpenAI-compatible Chat Completions path used by this JSON planner.
    model: str = "qwen3.8-flash"
    max_completion_tokens: int = 700
    max_calls_per_task: int = 4
    max_total_completion_tokens: int = 1_800
    max_context_chars: int = 9_000

    def __post_init__(self) -> None:
        if not 1 <= self.max_completion_tokens <= 900:
            raise ValueError("max_completion_tokens must be between 1 and 900")
        if not 1 <= self.max_calls_per_task <= 10:
            raise ValueError("max_calls_per_task must be between 1 and 10")
        if self.max_total_completion_tokens < self.max_completion_tokens:
            raise ValueError("total token budget must cover one call")
        if not 500 <= self.max_context_chars <= 12_000:
            raise ValueError("max_context_chars must be between 500 and 12000")


@dataclass(frozen=True)
class ModelPlan:
    kind: str
    tool: str | None
    arguments: dict[str, object]
    unified_diff: str | None
    reason: str
    completion_tokens: int


class BailianChatTransport:
    """Minimal OpenAI-compatible HTTP client; credentials are environment-only."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = base_url or os.getenv(
            "TRACEREPAIR_BAILIAN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        if not self._api_key:
            raise PlannerError("DASHSCOPE_API_KEY is not configured")

    def complete(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        request = Request(
            f"{self._base_url.rstrip('/')}/chat/completions",
            data=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - fixed configured endpoint
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # Keep a compact provider diagnostic, but never surface headers,
            # complete bodies, or credential-like values in terminal output.
            raise PlannerError(_http_error_detail(error)) from error
        except Exception as error:  # network/provider errors must not bypass safeguards
            raise PlannerError(f"model request failed: {type(error).__name__}") from error


class ModelPlanner:
    """Request one bounded model suggestion and persist only safe metadata."""

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
    ) -> ModelPlan:
        checkpoint = store.load_checkpoint(task_id)
        budget = dict(checkpoint.get("model_budget", {}))
        calls = int(budget.get("calls", 0))
        used_tokens = int(budget.get("completion_tokens", 0))
        if calls >= self._config.max_calls_per_task:
            raise BudgetExceeded("model call budget exhausted")
        if used_tokens + self._config.max_completion_tokens > self._config.max_total_completion_tokens:
            raise BudgetExceeded("model token budget exhausted")

        permitted = _ALLOWED_TOOLS if allowed_tools is None else allowed_tools
        if not permitted <= _ALLOWED_TOOLS:
            raise ValueError("allowed_tools must be a subset of the tool allowlist")
        payload = self._payload(evidence, permitted, allow_patch)
        response = self._transport.complete(payload)
        try:
            plan = self._parse_response(response)
        except PlannerError as error:
            self._record_model_result(
                task_id,
                store,
                checkpoint,
                calls,
                used_tokens,
                self._reported_completion_tokens(response),
                evidence,
                kind="invalid",
                tool=None,
                policy_accepted=False,
                parse_error=str(error),
                response_sha256=_response_content_sha256(response),
            )
            raise
        policy_error: str | None = None
        if plan.kind == "tool" and plan.tool not in permitted:
            policy_error = "model proposed a tool outside the current stage"
        elif plan.kind == "patch" and not allow_patch:
            policy_error = "model proposed a patch outside the patch stage"
        self._record_model_result(
            task_id,
            store,
            checkpoint,
            calls,
            used_tokens,
            plan.completion_tokens,
            evidence,
            kind=plan.kind,
            tool=plan.tool,
            policy_accepted=policy_error is None,
        )
        if policy_error:
            raise PlannerError(policy_error)
        return plan

    def _record_model_result(
        self,
        task_id: str,
        store: TraceStore,
        checkpoint: dict[str, Any],
        calls: int,
        used_tokens: int,
        completion_tokens: int,
        evidence: str,
        *,
        kind: str,
        tool: str | None,
        policy_accepted: bool,
        parse_error: str | None = None,
        response_sha256: str | None = None,
    ) -> None:
        checkpoint["model_budget"] = {
            "calls": calls + 1,
            "completion_tokens": used_tokens + completion_tokens,
            "max_calls": self._config.max_calls_per_task,
            "max_completion_tokens": self._config.max_total_completion_tokens,
        }
        store.save_checkpoint(task_id, checkpoint)
        payload: dict[str, object] = {
            "kind": kind,
            "tool": tool,
            "completion_tokens": completion_tokens,
            "prompt_chars": len(evidence[: self._config.max_context_chars]),
            "policy_accepted": policy_accepted,
        }
        if parse_error is not None:
            payload["parse_error"] = parse_error
        if response_sha256 is not None:
            payload["response_sha256"] = response_sha256
        store.append_event(
            task_id,
            "model_plan_recorded",
            payload,
        )

    def _payload(
        self, evidence: str, allowed_tools: set[str], allow_patch: bool
    ) -> dict[str, object]:
        clipped = evidence[: self._config.max_context_chars]
        forms = ['{"kind":"handoff","reason":"short"}']
        if allowed_tools:
            forms.insert(
                0,
                f'{{"kind":"tool","tool":"{"|".join(sorted(allowed_tools))}",'
                '"arguments":{},"reason":"short"}',
            )
        if allow_patch:
            forms.insert(1, '{"kind":"patch","unified_diff":"unified diff only","reason":"short"}')
        tool_rules: list[str] = []
        if "search_code" in allowed_tools:
            tool_rules.append(
                "search_code.query must be one plain literal substring such as read_bool or false; "
                "regex, wildcards, pipes, and OR expressions are unsupported."
            )
        if "read_file" in allowed_tools:
            tool_rules.append(
                "read_file.path must be an exact repository-relative path observed from a tool result."
            )
        if allow_patch:
            tool_rules.append(
                "unified_diff must begin with --- a/<path> or a standard diff --git line, and must "
                "contain --- a/<path>, +++ b/<path>, and an @@ hunk; do not use Begin Patch markers."
            )
        system = (
            "You are TraceRepair's planning component. Return exactly one JSON object, no markdown. "
            f"Allowed forms: {'; '.join(forms)}. "
            f"{' '.join(tool_rules)} "
            "Never claim tests passed. Never request shell, network, file writes, or test edits."
        )
        return {
            "model": self._config.model,
            "temperature": 0,
            "max_tokens": self._config.max_completion_tokens,
            # qwen3.8-flash defaults to thinking mode. This planner only needs
            # a compact schema-constrained routing decision, so reasoning is
            # explicitly disabled to prevent hidden completion-token spend.
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Evidence:\n{clipped}"},
            ],
        }

    def _parse_response(self, response: Mapping[str, object]) -> ModelPlan:
        try:
            choices = response["choices"]
            first = choices[0]  # type: ignore[index]
            content = first["message"]["content"]  # type: ignore[index]
            parsed = _decode_plan_object(str(content))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise PlannerError("model returned invalid structured output") from error
        completion_tokens = self._reported_completion_tokens(response)
        if not 0 <= completion_tokens <= self._config.max_completion_tokens:
            raise PlannerError("model response exceeded completion token limit")
        kind = parsed.get("kind")
        reason = parsed.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 500:
            raise PlannerError("model reason is invalid")
        # Small models occasionally use a harmless schema alias despite being
        # asked for the exact shape. Normalize only when the semantic action is
        # unique; ambiguous tool-plus-patch payloads remain denied.
        if kind in _ALLOWED_TOOLS:
            parsed = {**parsed, "tool": kind, "kind": "tool"}
            kind = "tool"
        elif kind in {"done", "final", "stop", "needs_human"}:
            kind = "handoff"
        elif kind not in {"tool", "patch", "handoff"}:
            tool = parsed.get("tool", parsed.get("action"))
            has_tool = tool in _ALLOWED_TOOLS
            has_patch = isinstance(parsed.get("unified_diff"), str)
            if has_tool == has_patch:
                raise PlannerError("model proposed an unknown or ambiguous plan kind")
            if has_tool:
                parsed = {**parsed, "tool": tool, "kind": "tool"}
                kind = "tool"
            else:
                kind = "patch"
        if kind == "tool":
            tool = parsed.get("tool")
            arguments = parsed.get("arguments", {})
            if tool not in _ALLOWED_TOOLS or not isinstance(arguments, dict):
                raise PlannerError("model proposed a denied tool")
            return ModelPlan("tool", tool, arguments, None, reason, completion_tokens)
        if kind == "patch":
            raw_diff = parsed.get("unified_diff")
            if not isinstance(raw_diff, str):
                raise PlannerError("model patch is not a string")
            diff = _normalize_unified_diff(raw_diff)
            if diff is None:
                raise PlannerError("model patch has invalid unified diff headers")
            return ModelPlan("patch", None, {}, diff, reason, completion_tokens)
        if kind == "handoff":
            return ModelPlan("handoff", None, {}, None, reason, completion_tokens)
        raise PlannerError("model proposed an unknown plan kind")

    @staticmethod
    def _reported_completion_tokens(response: Mapping[str, object]) -> int:
        usage = response.get("usage", {})
        if not isinstance(usage, Mapping):
            return 0
        try:
            return max(0, int(usage.get("completion_tokens", 0)))
        except (TypeError, ValueError):
            return 0


def _strip_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 : -3].strip()
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1]
    return stripped


def _decode_plan_object(content: str) -> dict[str, object]:
    """Decode exactly one semantic plan object, allowing harmless wrapper text."""

    stripped = _strip_fence(content)
    try:
        direct = json.loads(stripped)
    except json.JSONDecodeError:
        direct = None
    if isinstance(direct, dict):
        return direct
    if direct is not None:
        raise ValueError("plan response must be a JSON object")

    decoder = json.JSONDecoder()
    candidates: list[dict[str, object]] = []
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            decoded, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        if not {"kind", "tool", "action", "unified_diff"}.intersection(decoded):
            continue
        if decoded not in candidates:
            candidates.append(decoded)
    if len(candidates) != 1:
        raise ValueError("response must contain exactly one semantic plan object")
    return candidates[0]


def _http_error_detail(error: HTTPError) -> str:
    detail = f"model request rejected: HTTP {error.code}"
    try:
        raw = error.read().decode("utf-8", errors="replace")[:600]
        parsed = json.loads(raw)
        nested = parsed.get("error")
        candidate = parsed.get("message") or parsed.get("code")
        if not candidate and isinstance(nested, Mapping):
            candidate = nested.get("message") or nested.get("code")
        if isinstance(candidate, str) and candidate:
            safe = re.sub(r"sk-[A-Za-z0-9._-]+", "[redacted]", candidate)
            safe = " ".join(safe.split())[:240]
            return f"{detail} ({safe})"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    return detail


def _normalize_unified_diff(value: str) -> str | None:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline == -1:
            return None
        stripped = stripped[first_newline + 1 : -3].strip()
    if not stripped or len(stripped) > 12_000:
        return None
    valid_start = stripped.startswith("--- a/") or stripped.startswith("diff --git a/")
    if not valid_start:
        return None
    lines = stripped.splitlines()
    if not any(line.startswith("--- a/") for line in lines):
        return None
    if not any(line.startswith("+++ b/") for line in lines):
        return None
    if not any(line.startswith("@@") for line in lines):
        return None
    return stripped


def _response_content_sha256(response: Mapping[str, object]) -> str:
    try:
        choices = response["choices"]
        first = choices[0]  # type: ignore[index]
        content = str(first["message"]["content"])  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        content = ""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
