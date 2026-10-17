# Milestone 2-12: low-budget Model Studio planner

## Scope

The Model Studio client is deliberately a planner, not an executor. One model
response may suggest an allowlisted tool, supply a unified diff, or hand off to
a human. It cannot execute a shell command, write a file, mark a test passed,
or bypass the existing patch policy and repair workflow.

The default planner model is `qwen3.8-flash`: it is available in the configured
workspace, supports the OpenAI-compatible Chat Completions path used for strict
JSON planning, and is suited to the small first-stage requests.
`qwen-coder-turbo` is intentionally not used here; it is a
code-completions/FIM model with a different endpoint.

## Cost controls

- `temperature=0` for repeatable behaviour;
- `enable_thinking=false` and JSON-object output, preventing default hidden
  reasoning tokens on `qwen3.8-flash`;
- 700 completion tokens per request (hard cap: 900);
- at most four calls and 1,800 completion tokens per task by default;
- evidence clipped to 9,000 characters;
- only compact metadata and token counts enter SQLite traces; raw prompts and
  raw model outputs are not persisted.

## Connection

The adapter uses Model Studio's OpenAI-compatible Chat Completions endpoint.
Set `DASHSCOPE_API_KEY` only in the local environment and set
`TRACEREPAIR_BAILIAN_BASE_URL` to the workspace-specific Beijing endpoint.
No request is sent by tests or during application startup.

## Controlled execution bridge

`ModelGuidedWorkflow` maps an accepted tool suggestion only to the existing
instrumented tools. A model-produced patch is first moved through the same
`needs_human -> ready -> running` controlled repair entry as an externally
provided diff, then faces patch policy, target test, regression suite, and
human review. The model never receives a direct write or shell capability.

The live decision probe uses the same `InstrumentedTools` adapters for its
single allowed read-only action. A successful probe therefore persists both a
`model_plan_recorded` event and the normal tool lifecycle/checkpoint trace.
