"""Render an existing normalized baseline JSON as Markdown."""

import argparse
import hashlib
import json
from pathlib import Path

from evaluation.baseline import markdown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sidecar = args.run.with_suffix(args.run.suffix + ".sha256")
    if sidecar.is_file():
        expected = sidecar.read_text(encoding="ascii").split()[0]
        if hashlib.sha256(args.run.read_bytes()).hexdigest() != expected:
            raise ValueError("run report checksum mismatch")
    report = json.loads(args.run.read_text(encoding="utf-8"))
    rendered = markdown(report)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"Markdown report written: {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
