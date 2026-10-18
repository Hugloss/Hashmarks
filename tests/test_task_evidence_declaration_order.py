"""Bounded declaration disclosure preserves names and source-qualified context."""

from pathlib import Path

from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_tasks import RepositoryTasks
from hashmarks.codemap.task_evidence_initial import decode_initial_packet


def test_parameter_heavy_constructors_cannot_hide_named_operations(
    tmp_path: Path,
) -> None:
    for index in range(40):
        (tmp_path / f"a_factory_{index:02d}.py").write_text(
            f"class CallbackRouter{index}:\n"
            "    def __init__(self, archive, partitions, on_shutdown=None, on_close=None): pass\n"
        )
    (tmp_path / "z_archive.py").write_text(
        "class ArchiveCoordinator:\n"
        "    async def close(self):\n"
        "        for partition in self.partitions:\n"
        "            await partition.close()\n"
    )
    task = (
        "Archive shutdown closes partitions sequentially, so one partition "
        "prevents remaining partitions from closing."
    )
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(task)
        packets = [
            repository.tasks.evidence(task),
            decode_initial_packet(
                repository.tasks.evidence(task, result_mode="initial")
            ),
        ]
    for packet in packets:
        retrieval = assert_object(packet["retrieval"])
        rows = assert_records(retrieval["results"])
        assert any(
            row.get("path") == "z_archive.py"
            and row.get("symbol") == "ArchiveCoordinator.close"
            for row in rows[:3]
        )
        assert retrieval["ownership_authority"] is False
        assert assert_object(packet["ownership"])["owner"] == action["admitted_edit"]
        assert assert_object(packet["verification"])["selected"] == action["verify"]


def test_repeated_word_forms_do_not_manufacture_multiword_context(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "class SubscriberWorker:\n    def process(self, value): return value\n"
    )
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence("Subscribers subscriber subscribers")
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any(
        row.get("supplement") == "bounded-declaration-context" for row in rows
    )


def test_duplicate_context_qualification_preserves_the_existing_source_facts() -> None:
    natural: dict[str, object] = {
        "path": "worker.py",
        "qualname": "Worker.close",
        "start_line": 3,
        "end_line": 5,
        "score": 7.0,
        "ownership_authority": False,
        "future_qualification": {"unknown": None, "zero": 0},
        "retrieval_supplement": "bounded-natural-language",
    }
    context: dict[str, object] = {
        "path": "worker.py",
        "qualname": "Worker.close",
        "retrieval_supplement": "bounded-declaration-context",
    }
    combined = RepositoryTasks._task_evidence_combine_natural_supplements(
        [natural], context
    )
    assert len(combined) == 1
    assert combined[0]["retrieval_supplement"] == "bounded-declaration-context"
    assert combined[0]["future_qualification"] == {"unknown": None, "zero": 0}
    assert combined[0]["ownership_authority"] is False
    assert combined[0]["score"] == 7.0
    assert (combined[0]["start_line"], combined[0]["end_line"]) == (3, 5)
    assert natural["retrieval_supplement"] == "bounded-natural-language"
