import hashlib
import json

import pytest

from evaluation.baseline import build_report, markdown
from evaluation.report import main as report_main


def test_portfolio_report_separates_independent_bugs_and_repeats():
    report = build_report("portfolio_v1", "mixed-historical")
    summary = report["summary"]
    assert summary["observed_runs"] == 19
    assert summary["independent_bugs"] == 11
    assert summary["repeated_runs"] == 8
    assert summary["successes"] == 19
    assert summary["average_wall_seconds"] is None
    assert any(source["availability"] == "evidence_only_private_configuration" for source in report["sources"])


def test_current_report_keeps_failures_and_preserved_diff():
    report = build_report("current_v1", "0.8.5-dev1")
    assert report["summary"]["successes"] == 1
    assert report["summary"]["needs_human"] == 2
    tqdm = next(record for record in report["records"] if record["independent_bug_id"].endswith("tqdm-sizeless-bool"))
    assert not tqdm["success"] and tqdm["diff_evidence"] == "preserved"
    assert hashlib.sha256(tqdm["diff"].encode()).hexdigest() == tqdm["diff_sha256"]
    assert "candidate patch failed target test" in markdown(report)


def test_locked_report_is_three_independent_pass_at_one_attempts():
    report = build_report("locked_v1", "0.8.0")
    summary = report["summary"]
    assert summary["observed_runs"] == summary["independent_bugs"] == 3
    assert summary["repeated_runs"] == 0
    assert summary["successes"] == 2 and summary["needs_human"] == 1


def test_agent_version_mismatch_fails_closed():
    with pytest.raises(ValueError, match="requires agent-version"):
        build_report("current_v1", "0.8.4-dev1")


def test_report_renderer_rejects_tampered_run(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(build_report("current_v1", "0.8.5-dev1")), encoding="utf-8")
    path.with_suffix(".json.sha256").write_text("0" * 64 + "  run.json\n", encoding="ascii")
    monkeypatch.setattr("sys.argv", ["evaluation.report", "--run", str(path)])
    with pytest.raises(ValueError, match="checksum mismatch"):
        report_main()
