"""Write or verify the development protocol manifest for native function calling."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerepair.function_calling import FUNCTION_SCHEMAS, _canonical_sha256
from tracerepair.prompt_registry import prompt_manifest


OUTPUT = ROOT / "evaluation" / "protocols" / "native-function-calling-v0.8.0-dev1.json"
CONFIG = ROOT / "evaluation" / "configs" / "agent-v0.8.0-dev1.json"


def protocol_payload() -> dict[str, object]:
    source_paths = (
        "src/tracerepair/prompt_registry.py",
        "src/tracerepair/function_calling.py",
    )
    return {
        "schema_version": 1,
        "protocol_id": "native-function-calling-v0.8.0-dev1",
        "status": "development_contract_not_locked_evaluation",
        "agent_version": "0.8.0-dev1",
        "planner_protocol": "native_function_calling",
        "prompts": prompt_manifest(),
        "function_schemas": {
            name: {
                "sha256": _canonical_sha256(schema),
                "schema": schema,
            }
            for name, schema in sorted(FUNCTION_SCHEMAS.items())
        },
        "all_function_schemas_sha256": _canonical_sha256(FUNCTION_SCHEMAS),
        "agent_config": {
            "path": CONFIG.relative_to(ROOT).as_posix(),
            "sha256": _sha256(CONFIG),
        },
        "source_sha256": {
            relative: _sha256(ROOT / relative) for relative in source_paths
        },
        "execution_boundary": {
            "model_visible_functions": sorted(FUNCTION_SCHEMAS),
            "controller_only_operations": [
                "apply_patch",
                "run_tests",
                "run_regression",
                "state_transition",
            ],
            "model_has_execution_authority": False,
        },
        "claim_boundary": (
            "This manifest freezes a development protocol contract. It is not a repair-rate "
            "result and does not replace the published 0.7.0-dev2 locked evidence."
        ),
    }


def encoded_payload() -> bytes:
    return (json.dumps(protocol_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    encoded = encoded_payload()
    digest = hashlib.sha256(encoded).hexdigest()
    checksum = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
    if arguments.verify:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != encoded:
            raise SystemExit("protocol manifest does not match current prompts, schemas, or config")
        try:
            recorded = checksum.read_text(encoding="ascii").split()[0]
        except (OSError, IndexError) as error:
            raise SystemExit("protocol manifest checksum is missing") from error
        if recorded != digest:
            raise SystemExit("protocol manifest checksum mismatch")
        print(f"Protocol manifest verified: {digest}")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(encoded)
    checksum.write_text(f"{digest}  {OUTPUT.name}\n", encoding="ascii", newline="\n")
    print(f"Protocol manifest written: {OUTPUT.relative_to(ROOT)}")
    print(f"SHA-256: {digest}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
