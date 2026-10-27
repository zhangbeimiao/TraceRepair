import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "benchmarks" / "langgraph-blind-v0.7.0-dev2.json"
PREFLIGHT = (
    ROOT / "evaluation" / "frozen" / "langgraph-blind-v0.7.0-dev2-preflight.json"
)


def _manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_blind_manifest_uses_three_new_locked_repositories() -> None:
    blind = _manifest(MANIFEST)
    tasks = blind["tasks"]
    assert isinstance(tasks, list)

    assert blind["agent_version"] == "0.7.0-dev2"
    assert blind["model"] == "qwen3.8-flash"
    assert blind["protocol"] == "pass@1"
    assert len(tasks) == 3
    assert all(task["split"] == "locked" for task in tasks)
    assert len({task["source"]["repository_url"] for task in tasks}) == 3

    earlier_repositories: set[str] = set()
    for path in (ROOT / "evaluation" / "benchmarks").glob("*.json"):
        if path == MANIFEST:
            continue
        payload = _manifest(path)
        for task in payload.get("tasks", []):
            earlier_repositories.add(task["source"]["repository_url"])
    assert {
        task["source"]["repository_url"] for task in tasks
    }.isdisjoint(earlier_repositories)


def test_blind_task_harnesses_are_outside_model_write_allowlists() -> None:
    manifest = _manifest(MANIFEST)
    for task in manifest["tasks"]:
        config_path = (MANIFEST.parent / task["task_config"]).resolve()
        config = _manifest(config_path)
        allowlist = config["source_allowlist"]

        assert "tests" not in allowlist
        assert "glom/test" not in allowlist
        assert config["target_test"].split("::", 1)[0].startswith(
            ("tests/", "glom/test/")
        )


def test_blind_preflight_seal_matches_frozen_inputs() -> None:
    seal = _manifest(PREFLIGHT)
    manifest_bytes = MANIFEST.read_bytes()
    checksum = (
        PREFLIGHT.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]
    )

    assert hashlib.sha256(PREFLIGHT.read_bytes()).hexdigest() == checksum
    assert seal["status"] == "sealed_before_execution"
    assert seal["protocol"]["attempts_per_task"] == 1
    assert seal["protocol"]["retries_after_result"] is False
    assert seal["protocol"]["provider_requests_before_seal"] == 0
    assert seal["benchmark"]["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert seal["agent"]["config_sha256"] == hashlib.sha256(
        (ROOT / seal["agent"]["config_path"]).read_bytes()
    ).hexdigest()
    assert seal["agent"]["prompt_source_sha256"] == hashlib.sha256(
        (ROOT / seal["agent"]["prompt_source"]).read_bytes()
    ).hexdigest()
