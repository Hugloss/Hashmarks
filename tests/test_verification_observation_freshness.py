"""Optional task metadata cannot refresh a retained verification selection."""

from pathlib import Path

from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)


def test_stale_runner_metadata_preserves_task_selection_until_changed_set(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/engine.py").write_text(
        "def cobalt_value(): return 'old'\n", encoding="utf-8"
    )
    test_path = "tests/test_engine.py"
    (tmp_path / test_path).write_text(
        "from src.engine import cobalt_value\n"
        "def test_cobalt_value(): assert cobalt_value() == 'new'\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text("[tool.pytest.ini_options]\naddopts = '-q'\n", encoding="utf-8")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        before = repository.verification.nomination(test_path)
        generation = repository.store.generation()
        manifest.write_text(
            "[tool.pytest.ini_options]\naddopts = '-ra'\n", encoding="utf-8"
        )
        assert repository.index.is_current(test_path)
        assert repository.index.needs_reconcile("pyproject.toml")

        task = repository.tasks.evidence(
            "Change cobalt_value from old to new and verify cobalt_value",
            token_budget=512,
        )

        verification = assert_object(task["verification"])
        assert assert_object(verification["selected"])["path"] == test_path
        relevance = assert_object(verification["relevance"])
        candidate = next(
            row
            for row in assert_records(relevance["candidates"])
            if row["path"] == test_path
        )
        assert candidate["runner_available"] is False
        verifier_member = next(
            row
            for row in assert_records(candidate["supporting_source_members"])
            if row["path"] == test_path
        )
        assert verifier_member["member_revision"] == before["source_member_revision"]
        assert repository.store.generation() == generation
        assert repository.index.needs_reconcile("pyproject.toml")

        changed = repository.verification.changed_set(["src/engine.py"])

        assert repository.store.generation() > generation
        assert not repository.index.needs_reconcile("pyproject.toml")
        targets = assert_records(changed["targets"])
        assert [target["path"] for target in targets] == [test_path]
        nomination = assert_object(targets[0]["nomination"])
        assert nomination["available"] is True
        assert validate_verification_nomination(nomination)["valid"] is True
        assert nomination["nomination_identity"] != before["nomination_identity"]
        manifest_member = next(
            row
            for row in assert_records(nomination["supporting_source_members"])
            if row["path"] == "pyproject.toml"
        )
        current, _raw = repository.source.member("pyproject.toml")
        assert current["state"] == "known-present"
        assert manifest_member["member_revision"] == current["member_revision"]
