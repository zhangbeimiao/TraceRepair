"""Fail closed when a release candidate contains secrets, local paths, or large tracked files."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".cache",
    ".tmp",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "tmp",
    "traces",
    "workspaces",
}
TEXT_SUFFIXES = {
    ".css",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PATTERNS = {
    "API key literal": re.compile(r"\bsk-(?:ws-)?[A-Za-z0-9._-]{20,}"),
    "workspace-specific Bailian URL": re.compile(
        r"https://ws-[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com", re.IGNORECASE
    ),
    "absolute Windows user path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer credential": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
}
REQUIRED_FILES = {
    Path("evaluation/frozen/devset-v0.4.0-dev1.json"),
    Path("evaluation/frozen/testset-v0.4.0-dev1.json"),
    Path("evaluation/frozen/release-summary-v0.4.0-dev1.json"),
    Path("evaluation/frozen/failure-showcase-v0.4.0.json"),
    Path("evaluation/frozen/recovery-showcase-v0.4.1.json"),
    Path("examples/tasks/mini-repo.json"),
    Path("scripts/showcase.py"),
    Path("docs/releases/v0.6.0.md"),
    Path("docs/releases/v0.6.1.md"),
    Path("docs/agent-architecture.md"),
    Path("docs/interview-pitch.md"),
    Path("docs/patch-location-v0.6.0-dev1.md"),
    Path("docs/resume-material.md"),
    Path("evaluation/configs/agent-v0.6.0-dev1.json"),
    Path("evaluation/benchmarks/historical-python-v1.0.0.json"),
    Path("evaluation/frozen/agent-v0.5.0.json"),
    Path("evaluation/frozen/historical-python-v1.0.0.json"),
    Path("evaluation/frozen/historical-python-v1.0.0.json.sha256"),
    Path("evaluation/frozen/release-summary-v0.5.0.json"),
    Path("evaluation/results/historical-python-v1.0.0/attempts.jsonl"),
    Path("evaluation/results/historical-python-v1.0.0/report.json"),
    Path("evaluation/results/historical-python-v1.0.0/report.json.sha256"),
    Path("evaluation/frozen/repository-mini-repo-discount-v0.6.1.json"),
    Path("evaluation/frozen/locked-repository-v0.6.1.json"),
    Path("demo/dist/index.html"),
    Path("demo/dist/data.js"),
}
MAX_RELEASE_FILE_BYTES = 5 * 1024 * 1024


def release_files(root: Path):
    candidates = _tracked_paths(root) if (root / ".git").exists() else root.rglob("*")
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        yield path, relative


def _tracked_paths(root: Path):
    """Yield Git-tracked release inputs so ignored benchmark snapshots cannot affect a release."""

    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    for raw in completed.stdout.split(b"\0"):
        if raw:
            yield root / raw.decode("utf-8")


def verify(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    if sys.platform == "win32" and root.drive.upper() != "D:":
        violations.append(f"project root must stay on D:, got {root.drive or '<none>'}")
    for required in sorted(REQUIRED_FILES):
        if not (root / required).is_file():
            violations.append(f"missing required release artifact: {required.as_posix()}")

    for path, relative in release_files(root):
        if path.stat().st_size > MAX_RELEASE_FILE_BYTES:
            violations.append(
                f"release file exceeds 5 MiB: {relative.as_posix()} ({path.stat().st_size} bytes)"
            )
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            ".env.example",
            ".gitattributes",
            ".gitignore",
        }:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"release text file is not UTF-8: {relative.as_posix()}")
            continue
        for rule, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(content):
                violations.append(f"{rule}: {relative.as_posix()}")
    return sorted(set(violations))


def main() -> None:
    violations = verify()
    if violations:
        print("Release verification failed:")
        for violation in violations:
            print(f"- {violation}")
        raise SystemExit(1)
    scanned = sum(1 for _ in release_files(ROOT))
    print(f"Release verification passed. Scanned {scanned} files; no secret or size violation.")


if __name__ == "__main__":
    main()
