from tracerepair.showcase import ShowcaseTrace, showcase_steps


def test_showcase_steps_include_only_safe_execution_summaries() -> None:
    trace = ShowcaseTrace(
        task_id="model-agent-01-demo",
        case_id="01",
        issue="issue",
        status="awaiting_review",
        agent_version="0.4.0-dev1",
        model="qwen3.8-flash",
        events=(
            ("model_plan_recorded", {"kind": "patch", "completion_tokens": 80, "policy_accepted": True, "raw_response": "must-not-appear"}),
            ("tool_finished", {"tool": "apply_patch", "ok": True, "summary": {"files": ["src/eventrelay/idempotency.py"], "diff": "secret"}}),
        ),
    )
    rendered = "\n".join(showcase_steps(trace))
    assert "model -> patch" in rendered
    assert "files=['src/eventrelay/idempotency.py']" in rendered
    assert "must-not-appear" not in rendered
    assert "secret" not in rendered
