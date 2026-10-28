import hashlib
import json
from pathlib import Path

from tracerepair.benchmark_suite import BenchmarkManifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "evaluation/benchmarks/function-rag-locked-v0.8.0.json"
PREFLIGHT_PATH = ROOT / "evaluation/frozen/function-rag-locked-v0.8.0-preflight.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_locked_manifest_is_three_new_repositories_and_all_locked() -> None:
    manifest = BenchmarkManifest.load(MANIFEST_PATH)
    repositories = {task.source.repository_url for task in manifest.tasks}
    previously_used = {
        "https://github.com/pytoolz/toolz",
        "https://github.com/prettytable/prettytable",
        "https://github.com/mahmoud/glom",
        "https://github.com/tkem/cachetools",
        "https://github.com/un33k/python-slugify",
        "https://github.com/pallets/click",
    }

    assert manifest.agent_version == "0.8.0"
    assert len(manifest.tasks) == len(repositories) == 3
    assert all(task.split == "locked" for task in manifest.tasks)
    assert repositories.isdisjoint(previously_used)
    assert manifest.contracts is not None
    assert manifest.retrieval is not None


def test_preflight_binds_manifest_contracts_and_valid_oracles() -> None:
    manifest = BenchmarkManifest.load(MANIFEST_PATH)
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))

    assert preflight["manifest_sha256"] == manifest.manifest_sha256 == _sha256(MANIFEST_PATH)
    assert preflight["contracts"] == manifest.lock_payload()["contracts"]
    assert preflight["provider_requests"] == 0
    assert len(preflight["tasks"]) == 3
    assert all(task["buggy_exit_code"] == 1 for task in preflight["tasks"])
    assert all(task["fixed_target_passed"] for task in preflight["tasks"])
    assert all(task["fixed_regression_passed"] for task in preflight["tasks"])
    sidecar = PREFLIGHT_PATH.with_suffix(".json.sha256").read_text(encoding="utf-8")
    assert sidecar.split()[0] == _sha256(PREFLIGHT_PATH)
