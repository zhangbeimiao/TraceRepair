import subprocess
from pathlib import Path

import pytest

from evaluation.materialize import materialize_baseline, materialize_case
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.workflow import case_selector


def test_baseline_target_test_passes(tmp_path: Path) -> None:
    workspace = materialize_baseline(tmp_path / "baseline")
    runner = RestrictedTestRunner(workspace)
    result = runner.run_tests("tests/test_repair_targets.py::test_case_01_uses_event_id_for_idempotency")

    assert result.ok is True
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.error_code is None


def test_injected_case_is_reported_as_failed(tmp_path: Path) -> None:
    workspace = materialize_case("01", tmp_path / "case-01")
    runner = RestrictedTestRunner(workspace)
    result = runner.run_tests("tests/test_repair_targets.py::test_case_01_uses_event_id_for_idempotency")

    assert result.ok is False
    assert result.exit_code == 1
    assert result.error_code == "TEST_FAILED"
    assert "FAILED" in result.stdout


@pytest.mark.parametrize("case_id", ["01", "03", "05", "07", "10"])
def test_each_development_snapshot_fails_its_target(case_id: str, tmp_path: Path) -> None:
    workspace = materialize_case(case_id, tmp_path / f"case-{case_id}")

    result = RestrictedTestRunner(workspace).run_tests(case_selector(case_id))

    assert result.ok is False
    assert result.exit_code == 1
    assert result.error_code == "TEST_FAILED"


def test_regression_suite_is_fixed_and_passes_for_baseline(tmp_path: Path) -> None:
    workspace = materialize_baseline(tmp_path / "baseline")
    runner = RestrictedTestRunner(workspace)
    result = runner.run_regression()

    assert result.ok is True
    assert result.selector == "tests"


def test_arbitrary_pytest_arguments_are_denied(tmp_path: Path) -> None:
    workspace = materialize_baseline(tmp_path / "baseline")
    runner = RestrictedTestRunner(workspace)
    result = runner.run_tests("tests/test_repair_targets.py -k anything")

    assert result.ok is False
    assert result.error_code == "TEST_SELECTOR_DENIED"
    assert result.exit_code is None


def test_missing_pytest_config_is_structured_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "tests/test_repair_targets.py").write_text("", encoding="utf-8")
    runner = RestrictedTestRunner(workspace)

    result = runner.run_tests("tests/test_repair_targets.py")

    assert result.ok is False
    assert result.error_code == "PYTEST_CONFIG_NOT_FOUND"


def test_timeout_becomes_structured_result(monkeypatch, tmp_path: Path) -> None:
    workspace = materialize_baseline(tmp_path / "baseline")
    runner = RestrictedTestRunner(workspace, timeout_seconds=1)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=b"partial output")

    monkeypatch.setattr("tracerepair.test_runner.subprocess.run", timeout)
    result = runner.run_tests("tests/test_repair_targets.py")

    assert result.ok is False
    assert result.timed_out is True
    assert result.error_code == "TEST_TIMEOUT"
    assert result.stdout == "partial output"


def test_test_process_does_not_receive_provider_or_cloud_credentials(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = materialize_baseline(tmp_path / "baseline")
    captured_environment = {}
    monkeypatch.setenv("DASHSCOPE_API_KEY", "secret-dashscope")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-aws")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-github")

    def completed(*args, **kwargs):
        captured_environment.update(kwargs["env"])
        return subprocess.CompletedProcess(args[0], 0, "passed", "")

    monkeypatch.setattr("tracerepair.test_runner.subprocess.run", completed)
    result = RestrictedTestRunner(workspace).run_tests("tests/test_repair_targets.py")

    assert result.ok is True
    assert "DASHSCOPE_API_KEY" not in captured_environment
    assert "OPENAI_API_KEY" not in captured_environment
    assert "AWS_SECRET_ACCESS_KEY" not in captured_environment
    assert "GITHUB_TOKEN" not in captured_environment
    assert captured_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
