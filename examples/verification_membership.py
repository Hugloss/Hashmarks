"""Observe supplied neutral collection fixtures; no native collector is executed."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from hashmarks import CodeMap, validate_native_consumer_bundle


def _supplied_report(repository: CodeMap) -> dict[str, object]:
    inputs = []
    for path in ("tests/test_example.py", "pyproject.toml"):
        member, _ = repository.source.member(path)
        inputs.append({"path": path, "member_revision": member["member_revision"]})
    return {
        "schema": "hashmarks.verification-membership-report.v1",
        "selection_kind": "native-collected",
        "producer": {"name": "supplied-example-fixture"},
        "provenance": {"report_id": "example:1", "synthetic": True},
        "scope": {"paths": ["tests/test_example.py"]},
        "status": "succeeded",
        "completeness": "complete",
        "truncation": "complete",
        "members": [
            {"path": "tests/test_example.py", "test_symbol": "test_value[a::b]"}
        ],
        "inputs": inputs,
    }


def _summary(observation: dict[str, object]) -> dict[str, object]:
    validation = validate_native_consumer_bundle(observation)
    assert validation["valid"], validation["reasons"]
    return {
        "membership": observation["membership"],
        "source_equivalence": observation["source_equivalence"],
        "repository": observation["repository"],
        "report": observation["report"],
        "membership_authority": observation["membership_authority"],
        "repository_absence": observation["repository_absence"],
    }


def run_example() -> dict[str, object]:
    """Return public observations for reproducible synthetic collection claims."""
    with TemporaryDirectory(prefix="hashmarks-membership-example-") as directory:
        root = Path(directory)
        workspace = root / "repository"
        (workspace / "tests").mkdir(parents=True)
        source = workspace / "tests/test_example.py"
        source.write_text("def test_value(): pass\n", encoding="utf-8")
        (workspace / "pyproject.toml").write_text(
            '[project]\nname="example"\nversion="1"\n', encoding="utf-8"
        )
        with CodeMap(workspace, state_dir=root / "state") as repository:
            repository.index.sync()
            report = _supplied_report(repository)
            matching = repository.verification.observe_membership(report)
            incomplete = deepcopy(report)
            incomplete.update(
                status="failed", completeness="incomplete", truncation="unknown"
            )
            partial = repository.verification.observe_membership(incomplete)
            empty = deepcopy(report)
            empty["members"] = []
            no_members = repository.verification.observe_membership(empty)
            source.write_text("def test_value(): return 'changed'\n", encoding="utf-8")
            repository.index.sync(["tests/test_example.py"])
            changed = repository.verification.observe_membership(report)
            return {
                "matching": _summary(matching),
                "changed": _summary(changed),
                "incomplete": _summary(partial),
                "empty": _summary(no_members),
            }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run_example(), indent=2) + "\n")
