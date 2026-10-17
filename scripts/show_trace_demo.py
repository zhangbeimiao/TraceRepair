"""Print a presentation-safe timeline from a real persisted TraceRepair run."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.showcase import load_showcase_trace, render_showcase


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", help="trace task id; defaults to the latest model-agent run")
    arguments = parser.parse_args()
    trace = load_showcase_trace(ROOT / "data" / "model-agent.sqlite3", arguments.task_id)
    print(render_showcase(trace))


if __name__ == "__main__":
    main()
