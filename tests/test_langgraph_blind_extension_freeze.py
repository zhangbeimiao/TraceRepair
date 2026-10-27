import hashlib
import json
from pathlib import Path

from scripts.verify_blind_evidence import verify_blind_evidence


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "langgraph-blind-extension-v0.7.0-dev2"


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extension_is_frozen_as_one_shot_evidence() -> None:
    frozen_path = ROOT / "evaluation" / "frozen" / f"{BENCHMARK}.json"
    frozen = _json(frozen_path)
    checksum = frozen_path.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]

    assert _sha256(frozen_path) == checksum
    assert frozen["summary"]["attempted_tasks"] == 3
    assert frozen["summary"]["successes"] == 1
    assert frozen["summary"]["human_handoffs"] == 2
    assert frozen["summary"]["incorrect_accepted_patches"] == 0
    assert frozen["splits"]["locked"]["one_shot"] is True
    assert frozen["splits"]["locked"]["retried"] is False


def test_extension_artifacts_match_trace_hashes() -> None:
    result = ROOT / "evaluation" / "results" / BENCHMARK
    cachetools = _json(result / "failures" / "cachetools-falsey-getsizeof.json")
    click = _json(result / "failures" / "click-sentinel-copy.json")
    slugify = _json(result / "successes" / "python-slugify-invalid-types.json")

    assert cachetools["candidate_diff_present"] is False
    assert click["candidate_diff_present"] is False
    assert cachetools["target_test_started"] is False
    assert click["target_test_started"] is False
    assert len(cachetools["model_response"]["response_sha256"]) == 64
    assert len(click["model_response"]["response_sha256"]) == 64
    published = result / "successes" / "python-slugify-invalid-types.diff"
    assert _sha256(published) == slugify["candidate"]["published_sha256"]
    assert slugify["candidate"]["trace_sha256"] == (
        "a2483b532066bfb7e0603b031e0b16072ae4d92da6b012e177d996694d533aa5"
    )
    assert slugify["target_test"]["passed"] is True
    assert slugify["regression_test"]["passed"] is True


def test_six_repository_aggregate_is_derived_from_both_cohorts() -> None:
    verified = verify_blind_evidence(ROOT)

    assert verified["tasks"] == 6
    assert verified["successes"] == 2
    assert verified["human_handoffs"] == 4
    assert verified["incorrect_accepted_patches"] == 0
    assert len(verified["cohorts"]) == 2
