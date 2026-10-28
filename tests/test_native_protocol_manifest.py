import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_protocol_manifest.py"
MANIFEST = ROOT / "evaluation" / "protocols" / "native-function-calling-v0.8.0-dev1.1.json"


def _module():
    spec = importlib.util.spec_from_file_location("freeze_protocol_manifest", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_protocol_manifest_matches_current_sources() -> None:
    module = _module()
    expected = module.encoded_payload()
    assert MANIFEST.read_bytes() == expected
    checksum = MANIFEST.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]
    assert checksum == hashlib.sha256(expected).hexdigest()
    payload = json.loads(expected)
    assert payload["status"] == "development_contract_not_locked_evaluation"
    assert len(payload["prompts"]) == 3
    assert len(payload["function_schemas"]) == 5
    assert payload["execution_boundary"]["model_has_execution_authority"] is False
    assert payload["execution_boundary"]["proposal_only_aliases"] == {
        "apply_patch": "propose_patch"
    }
