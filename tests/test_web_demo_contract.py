import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "demo" / "dist"


def _payload() -> dict[str, object]:
    source = (DIST / "data.js").read_text(encoding="utf-8")
    prefix = "window.TRACEREPAIR_DEMO = "
    assert source.startswith(prefix)
    assert source.endswith(";\n")
    return json.loads(source[len(prefix) : -2])


def test_public_demo_contains_verified_patches_and_frozen_failures() -> None:
    payload = _payload()

    assert len(payload["traces"]) == 13
    assert len(payload["failures"]) == 3
    assert len(payload["recoveryScenarios"]) == 2
    assert payload["repositoryCohort"]["runs"] == 5
    assert payload["repositoryCohort"]["successes"] == 5
    assert payload["repositoryCohort"]["averageTokens"] == 179.6
    assert payload["lockedRepositoryResult"]["success"] is True
    assert payload["lockedRepositoryResult"]["oneShot"] is True
    assert payload["lockedRepositoryResult"]["retried"] is False
    assert payload["lockedRepositoryResult"]["tokens"] == 234
    assert {failure["category"] for failure in payload["failures"]} == {
        "patch_context_mismatch",
        "diagnosis_budget_exhausted",
        "invalid_patch_output",
    }
    for trace in payload["traces"]:
        assert trace["patchPreview"]["file"].startswith("src/eventrelay/")
        assert trace["patchPreview"]["lines"]
        assert len(trace["patchPreview"]["contentSha256"]) == 64
        assert all(trace["verification"][gate]["ok"] for gate in ("policy", "apply", "target", "regression"))
    for failure in payload["failures"]:
        assert failure["status"] == "needs_human"
        assert failure["control"]["patchApplied"] is False
        assert failure["control"]["testsStarted"] is False
    for scenario in payload["recoveryScenarios"]:
        assert scenario["final_status"] == "awaiting_review"
        assert len(scenario["final_tools"]) == len(set(scenario["final_tools"]))
    patch_resume = next(
        item for item in payload["recoveryScenarios"] if item["crash_point"] == "patch_applied"
    )
    assert patch_resume["resume_model_calls"] == 0
    assert patch_resume["skipped_tools"] == ["apply_patch"]


def test_public_demo_excludes_local_paths_and_raw_model_fields() -> None:
    serialized = json.dumps(_payload(), ensure_ascii=False)

    assert "C:\\Users\\" not in serialized
    assert "D:\\AI-Agent-Intern" not in serialized
    assert "raw_response" not in serialized
    assert "DASHSCOPE_API_KEY" not in serialized
    assert "sk-ws-" not in serialized


def test_demo_page_exposes_diff_and_failure_controls() -> None:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    script = (DIST / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "diff-code",
        "failure-tabs",
        "failure-timeline",
        "failure-outcome",
        "failure-lesson",
        "recovery-tabs",
        "recovery-timeline",
        "recovery-skipped",
        "repository-evidence-label",
        "repository-score",
        "repository-detail",
        "locked-repository-evidence-label",
        "locked-repository-score",
        "locked-repository-detail",
    ):
        assert html.count(f'id="{element_id}"') == 1
        assert f'#{element_id}' in script
    assert html.count('id="verification-grid"') == 1
    for gate in ("policy", "apply", "target", "regression"):
        assert f'id="verify-{gate}"' in html
    assert "#verify-${name}" in script
