"""A bounded pytest runner for self-owned EventRelay case workspaces only."""

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_TARGET_SELECTOR = re.compile(
    r"^tests/test_repair_targets\.py(?:::test_case_(?:0[1-9]|10)_[A-Za-z0-9_]+)?$"
)


@dataclass(frozen=True)
class TestRunResult:
    ok: bool
    selector: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    stdout: str
    stderr: str
    output_truncated: bool
    error_code: str | None = None


class RestrictedTestRunner:
    """Run only known target tests from a trusted, disposable workspace.

    This is command injection resistant because no user input becomes a shell
    command or pytest option. It is not a replacement for OS/container sandboxing:
    until that later milestone, it must only execute self-owned EventRelay cases.
    """

    def __init__(self, workspace: Path, *, timeout_seconds: int = 30, output_limit: int = 8_000) -> None:
        resolved = workspace.resolve()
        if not resolved.is_dir():
            raise ValueError(f"workspace does not exist: {workspace}")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        self._workspace = resolved
        self._timeout_seconds = timeout_seconds
        self._output_limit = output_limit

    def run_tests(self, selector: str) -> TestRunResult:
        if not _TARGET_SELECTOR.fullmatch(selector):
            return TestRunResult(
                ok=False,
                selector=selector,
                exit_code=None,
                timed_out=False,
                duration_ms=0,
                stdout="",
                stderr="",
                output_truncated=False,
                error_code="TEST_SELECTOR_DENIED",
            )
        test_file = (self._workspace / selector.split("::", 1)[0]).resolve()
        if not test_file.is_file() or not test_file.is_relative_to(self._workspace):
            return TestRunResult(
                ok=False,
                selector=selector,
                exit_code=None,
                timed_out=False,
                duration_ms=0,
                stdout="",
                stderr="",
                output_truncated=False,
                error_code="TEST_FILE_NOT_FOUND",
            )

        return self._run("target", selector)

    def run_regression(self) -> TestRunResult:
        test_directory = (self._workspace / "tests").resolve()
        if not test_directory.is_dir() or not test_directory.is_relative_to(self._workspace):
            return TestRunResult(
                ok=False,
                selector="tests",
                exit_code=None,
                timed_out=False,
                duration_ms=0,
                stdout="",
                stderr="",
                output_truncated=False,
                error_code="REGRESSION_TESTS_NOT_FOUND",
            )
        return self._run("regression", "tests")

    def _run(self, _kind: str, selector: str) -> TestRunResult:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self._workspace / "src")
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        temporary_directory = self._workspace / ".tmp"
        temporary_directory.mkdir(exist_ok=True)
        environment["TMP"] = str(temporary_directory)
        environment["TEMP"] = str(temporary_directory)
        config_file = self._workspace / "pytest.ini"
        if not config_file.is_file():
            config_file = self._workspace / "pyproject.toml"
        if not config_file.is_file():
            return TestRunResult(
                ok=False,
                selector=selector,
                exit_code=None,
                timed_out=False,
                duration_ms=0,
                stdout="",
                stderr="",
                output_truncated=False,
                error_code="PYTEST_CONFIG_NOT_FOUND",
            )
        command = [sys.executable, "-m", "pytest", "-c", str(config_file), selector, "-q"]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self._workspace,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            duration = int((time.monotonic() - started) * 1_000)
            stdout, stdout_cut = self._trim(error.stdout)
            stderr, stderr_cut = self._trim(error.stderr)
            return TestRunResult(
                ok=False,
                selector=selector,
                exit_code=None,
                timed_out=True,
                duration_ms=duration,
                stdout=stdout,
                stderr=stderr,
                output_truncated=stdout_cut or stderr_cut,
                error_code="TEST_TIMEOUT",
            )

        duration = int((time.monotonic() - started) * 1_000)
        stdout, stdout_cut = self._trim(completed.stdout)
        stderr, stderr_cut = self._trim(completed.stderr)
        return TestRunResult(
            ok=completed.returncode == 0,
            selector=selector,
            exit_code=completed.returncode,
            timed_out=False,
            duration_ms=duration,
            stdout=stdout,
            stderr=stderr,
            output_truncated=stdout_cut or stderr_cut,
            error_code=None if completed.returncode == 0 else "TEST_FAILED",
        )

    def _trim(self, output: str | bytes | None) -> tuple[str, bool]:
        if output is None:
            return "", False
        text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
        if len(text) <= self._output_limit:
            return text, False
        marker = "\n...[output truncated]"
        return text[: self._output_limit - len(marker)] + marker, True
