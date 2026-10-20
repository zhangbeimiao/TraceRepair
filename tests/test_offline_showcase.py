from scripts.showcase import load_demo_data, render_showcase


def test_offline_showcase_replays_all_evidence_without_private_metadata() -> None:
    output = render_showcase(load_demo_data())

    assert "provider requests: 0" in output
    assert "Real historical bugs, pass@1   : 2/3 passed; 1 safely rejected" in output
    assert "0 incorrect patches accepted; 1 human handoff" in output
    assert "PATCH_CONTEXT_MISMATCH" in output
    assert "EventRelay controlled regression: 13/13 passed" in output
    assert "Public configured repository    : 5/5 passed" in output
    assert "Held-out repository, one shot   : 1/1 passed" in output
    assert "search_code -> read_file -> apply_patch -> run_tests -> run_regression" in output
    assert "PATCH_CONTEXT_MISMATCH" in output
    assert "model_calls=0, skipped=apply_patch" in output
    assert "After resume : run_tests -> run_regression" in output
    assert "repository writes: 0" in output
    assert "new agent version and a new frozen benchmark" in output
    assert "ledgerlite" not in output.lower()


def test_offline_showcase_can_render_one_section_and_case() -> None:
    output = render_showcase(load_demo_data(), section="repair", case_id="10")

    assert "case 10 (batch-isolation)" in output
    assert "[1] FROZEN EVIDENCE" not in output
    assert "[3] SAFE FAILURE" not in output
