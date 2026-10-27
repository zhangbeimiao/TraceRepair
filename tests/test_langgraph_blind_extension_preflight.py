import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "evaluation"
    / "benchmarks"
    / "langgraph-blind-extension-v0.7.0-dev2.json"
)
PREFLIGHT = (
    ROOT
    / "evaluation"
    / "frozen"
    / "langgraph-blind-extension-v0.7.0-dev2-preflight.json"
)


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_extension_uses_three_new_locked_repositories() -> None:
    extension = _json(MANIFEST)
    tasks = extension["tasks"]
    assert isinstance(tasks, list)

    assert extension["agent_version"] == "0.7.0-dev2"
    assert extension["model"] == "qwen3.8-flash"
    assert extension["protocol"] == "pass@1"
    assert len(tasks) == 3
    assert all(task["split"] == "locked" for task in tasks)
    assert len({task["source"]["repository_url"] for task in tasks}) == 3

    earlier_repositories: set[str] = set()
    for path in (ROOT / "evaluation" / "benchmarks").glob("*.json"):
        if path == MANIFEST:
            continue
        payload = _json(path)
        for task in payload.get("tasks", []):
            earlier_repositories.add(task["source"]["repository_url"])
    assert {
        task["source"]["repository_url"] for task in tasks
    }.isdisjoint(earlier_repositories)


def test_extension_harnesses_are_outside_model_write_allowlists() -> None:
    manifest = _json(MANIFEST)
    for task in manifest["tasks"]:
        config_path = (MANIFEST.parent / task["task_config"]).resolve()
        config = _json(config_path)
        test_path = PurePosixPath(config["target_test"].split("::", 1)[0])
        allowlist = [PurePosixPath(item) for item in config["source_allowlist"]]

        assert not any(test_path == root or root in test_path.parents for root in allowlist)


def test_extension_preflight_seal_matches_frozen_inputs() -> None:
    seal = _json(PREFLIGHT)
    checksum = (
        PREFLIGHT.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]
    )

    assert hashlib.sha256(PREFLIGHT.read_bytes()).hexdigest() == checksum
    assert seal["status"] == "sealed_before_execution"
    assert seal["protocol"]["task_count"] == 3
    assert seal["protocol"]["attempts_per_task"] == 1
    assert seal["protocol"]["retries_after_result"] is False
    assert seal["protocol"]["provider_requests_before_seal"] == 0
    assert seal["benchmark"]["manifest_sha256"] == hashlib.sha256(
        MANIFEST.read_bytes()
    ).hexdigest()
    assert seal["agent"]["config_sha256"] == hashlib.sha256(
        (ROOT / seal["agent"]["config_path"]).read_bytes()
    ).hexdigest()
    assert seal["agent"]["prompt_source_sha256"] == hashlib.sha256(
        (ROOT / seal["agent"]["prompt_source"]).read_bytes()
    ).hexdigest()
