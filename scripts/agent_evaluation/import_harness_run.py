from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.agent_evaluation.experiment import ExperimentLane, import_native_run


def main() -> int:
    p = argparse.ArgumentParser(
        description="Normalize an externally executed harness JSONL run into a Hashmarks experiment bundle."
    )
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--lane", required=True)
    p.add_argument("--model", required=True)
    p.add_argument(
        "--strategy", choices=("native", "hashmarks", "selective-scout"), required=True
    )
    p.add_argument("--effort")
    p.add_argument("--task-id", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--repository-identity")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    lane = ExperimentLane(a.lane, a.harness, a.model, a.strategy, a.effort)
    value = import_native_run(
        lane=lane,
        task_id=a.task_id,
        session_id=a.session_id,
        repository_identity=a.repository_identity,
        event_path=a.events,
    )
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)
    print(text, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
