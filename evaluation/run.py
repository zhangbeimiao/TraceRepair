"""Build a deterministic JSON and Markdown report from frozen evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from evaluation.baseline import ROOT, build_report, markdown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--agent-version", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.suite, args.agent_version)
    output = args.output or ROOT / "runs" / f"{args.suite}.json"
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    output.with_suffix(".md").write_text(markdown(report), encoding="utf-8", newline="\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii", newline="\n"
    )
    print(f"Frozen evidence report written: {output.relative_to(ROOT)}")
    print(f"runs={report['summary']['observed_runs']} independent_bugs={report['summary']['independent_bugs']} repeated={report['summary']['repeated_runs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
