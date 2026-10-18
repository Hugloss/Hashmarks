"""Task-local source excerpts retain exact source and no execution authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response

TASK = "A cached stream adapter accepts unsupported settings. Inspect adapter.py."
GUARD = "        if has_stream and use_cache:"


def _write(root: Path, *, guard: str = GUARD) -> None:
    (root / "adapter.py").write_text(
        "class Adapter:\n"
        "    def __init__(self, has_stream, use_cache):\n"
        + guard
        + "\n            raise ValueError('unsupported settings')\n"
        "        self.use_cache = use_cache\n"
    )


def _logical(packet: Mapping[str, object]) -> Mapping[str, object]:
    return decode_initial_packet(packet) if "encoding" in packet else packet


def _source(packet: Mapping[str, object]) -> dict[str, object]:
    retrieval = assert_object(_logical(packet)["retrieval"])
    row = next(
        row
        for row in assert_records(retrieval["results"])
        if row["path"] == "adapter.py"
    )
    return assert_object(row["source_observation"])


@pytest.mark.parametrize("mode", ["default", "initial"])
@pytest.mark.parametrize("limit", [1, 3, 20])
def test_literal_task_exposes_the_exact_guard_without_owner_or_runtime_inference(
    tmp_path: Path, mode: str, limit: int
) -> None:
    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(TASK, limit=limit)
        packet = repository.tasks.evidence(TASK, result_mode=mode, limit=limit)
    source = _source(packet)
    assert (
        assert_object(source["member"])["member_revision"]
        == hash_file(tmp_path / "adapter.py", domain=FILE_DOMAIN).hash
    )
    anchor = next(
        row for row in assert_records(source["line_anchors"]) if row["line"] == 3
    )
    assert (
        anchor["line_sha256"]
        == hashlib.sha256(b"hashmarks.source-line.v1\0" + GUARD.encode()).hexdigest()
    )
    assert any(
        row["text"] == GUARD for row in assert_records(anchor["context_excerpt"])
    )
    assert source["authority"] == "repository-evidence-only"
    assert source["execution_effect"] == "none"
    logical = _logical(packet)
    owner = assert_object(logical["ownership"])
    admitted = action["admitted_edit"]
    assert admitted is not None
    assert assert_object(owner["owner"])["path"] == admitted["path"]
    assert (
        owner["authority_proof_identity"]
        == action["ownership_authority"]["authority_proof_identity"]
    )
    for format in FORMATS:
        response = presentation_response(
            "task_evidence", packet, result_mode=mode, format=format
        )
        native = assert_object(response.get("result", response))
        assert _source(native) == source
        if format != "none":
            assert GUARD in json.dumps(response["presentation"])


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_source_context_respects_source_visibility(
    tmp_path: Path, visibility: str
) -> None:
    _write(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern = "adapter.py"\nvisibility = "{visibility}"\n'
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    assert GUARD not in json.dumps(_logical(packet))
    assert "source_observation" not in json.dumps(_logical(packet))


def test_comments_and_strings_cannot_nominate_source_anchors(tmp_path: Path) -> None:
    _write(tmp_path)
    file = tmp_path / "adapter.py"
    file.write_text(
        "# cached stream adapter settings\nTEXT = 'cached stream settings'\n"
        + file.read_text()
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        source = _source(repository.tasks.evidence(TASK))
    assert all(
        row["line"] not in {1, 2} for row in assert_records(source["line_anchors"])
    )


def test_reopened_source_context_does_not_replay_the_old_guard(tmp_path: Path) -> None:
    _write(tmp_path)
    state = tmp_path / ".hashmarks" / "state"
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        before = _source(repository.tasks.evidence(TASK))
    _write(tmp_path, guard="        if has_stream and not use_cache:")
    with CodeMap(tmp_path, state_dir=state) as repository:
        after = _source(repository.tasks.evidence(TASK, result_mode="initial"))
    assert (
        assert_object(before["member"])["member_revision"]
        != assert_object(after["member"])["member_revision"]
    )
    assert "not use_cache" in json.dumps(after)


def test_excerpt_bound_accounts_for_omitted_matches_without_negative_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "adapter.py").write_text(
        "def adapter(use_cache, has_stream):\n"
        + "".join("    use_cache(has_stream)\n" for _ in range(10))
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    row = next(
        row
        for row in assert_records(
            assert_object(_logical(packet)["retrieval"])["results"]
        )
        if row["path"] == "adapter.py"
    )
    selection = assert_object(row["source_selection"])
    assert (
        selection["observed_candidates_in_scanned_nodes"],
        selection["returned"],
        selection["omitted_candidates_in_scanned_nodes"],
    ) == (10, 3, 7)
    assert selection["coverage"] == "incomplete"
    assert selection["negative_evidence_admissible"] is False
    assert len(assert_records(_source(packet)["line_anchors"])) == 3


def test_incomplete_ast_lookup_is_visible_even_without_selected_lines(
    tmp_path: Path,
) -> None:
    (tmp_path / "adapter.py").write_text(
        "".join(f"UNRELATED_{i} = {i}\n" for i in range(2000))
        + "def adapter(use_cache, has_stream):\n    return use_cache(has_stream)\n"
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    row = next(
        row
        for row in assert_records(
            assert_object(_logical(packet)["retrieval"])["results"]
        )
        if row["path"] == "adapter.py"
    )
    selection = assert_object(row["source_selection"])
    assert selection["candidate_nodes_truncated"] is True
    assert selection["coverage"] == "incomplete"
    assert selection["negative_evidence_admissible"] is False
    assert "source_observation" not in row
    text = assert_object(
        presentation_response(
            "task_evidence", packet, result_mode="initial", format="text"
        )["presentation"]
    )["text"]
    assert '"candidate_nodes_truncated":true' in str(text)
