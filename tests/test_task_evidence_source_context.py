"""Task-local source excerpts retain exact source and no execution authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import (
    assert_array,
    assert_integer,
    assert_object,
    assert_records,
)

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response
from hashmarks.python_ast_cache import PythonAstSnapshot

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


def _pointer(value: object, pointer: str) -> object:
    for part in pointer.lstrip("/").split("/") if pointer else []:
        key = part.replace("~1", "/").replace("~0", "~")
        value = (
            value[int(key)] if isinstance(value, list) else assert_object(value)[key]
        )
    return value


@pytest.mark.parametrize("format", ["compact", "text"])
def test_source_view_recovers_every_native_value_and_future_metadata(
    tmp_path: Path, format: str
) -> None:
    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = decode_initial_packet(
            repository.tasks.evidence(TASK, result_mode="initial")
        )
    source = _source(packet)
    source["future/key~"] = {"false": False, "zero": 0.0, "unknown": None}
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = encode_initial_packet(packet)
    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format=format
    )
    projection = assert_object(response["presentation"])
    if format == "compact":
        group = next(
            group
            for group in assert_records(projection["groups"])
            if group["family"] == "source"
        )
        view = assert_object(assert_records(group["findings"])[0]["details"])
    else:
        line = next(
            line
            for line in str(projection["text"]).splitlines()
            if line.startswith("Source observation @ ")
        )
        view = assert_object(json.loads(line.partition(": ")[2]))
    recovered = deepcopy(assert_object(_pointer(packet, str(view["metadata_ref"]))))
    displayed = deepcopy(view)
    shared = assert_object(displayed.pop("line_anchor_qualifiers", {}))
    anchors = []
    for raw_anchor in assert_records(displayed["line_anchors"]):
        anchor = {**shared, **raw_anchor}
        context_shared = assert_object(anchor.pop("context_excerpt_qualifiers", {}))
        anchor["context_excerpt"] = [
            {**context_shared, **row}
            for row in assert_records(anchor["context_excerpt"])
        ]
        anchors.append(anchor)
    displayed["line_anchors"] = anchors
    recovered.update(
        {key: value for key, value in displayed.items() if key != "metadata_ref"}
    )
    assert json.dumps(recovered, sort_keys=True) == json.dumps(source, sort_keys=True)
    assert displayed["line_anchors"] == source["line_anchors"]
    assert view["freshness"] == source["freshness"]
    assert view["negative_evidence"] == source["negative_evidence"]
    assert decode_initial_packet(assert_object(response["result"])) == packet


def test_task_source_packet_is_the_canonical_source_observation(tmp_path: Path) -> None:
    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK)
        observed = _source(packet)
        expected = repository.source.observe(
            "adapter.py",
            lines=tuple(
                assert_integer(line)
                for line in assert_array(observed["requested_lines"])
            ),
            anchor_context_lines=1,
            max_bytes=262_144,
        )
    assert _source(packet) == expected


def test_source_change_between_candidate_lookup_and_observation_restarts_the_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hashmarks.codemap import task_evidence_source_context

    _write(tmp_path)
    original = task_evidence_source_context.read_python_ast
    changed = False

    def read(path: Path) -> PythonAstSnapshot:
        nonlocal changed
        snapshot = original(path)
        if not changed:
            changed = True
            _write(tmp_path, guard="        if has_stream and not use_cache:")
        return snapshot

    monkeypatch.setattr(task_evidence_source_context, "read_python_ast", read)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    source = _source(packet)
    assert changed
    assert (
        assert_object(source["member"])["member_revision"]
        == hash_file(tmp_path / "adapter.py", domain=FILE_DOMAIN).hash
    )
    assert "if has_stream and not use_cache:" in json.dumps(source)


def test_output_format_directive_does_not_change_source_selection(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        before = _source(repository.tasks.evidence(TASK))
        after = _source(
            repository.tasks.evidence(
                TASK + " Return exactly JSON.", result_mode="initial"
            )
        )
    assert before == after


@pytest.mark.parametrize("state", ["unsupported", "unknown"])
def test_source_refusal_overrides_current_index_hints_before_ast_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    from hashmarks.codemap import task_evidence_source_context

    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        assert repository.index.is_current("adapter.py")

        def member(
            path: str, *, include_bytes: bool = False
        ) -> tuple[dict[str, object], bytes | None]:
            return {"path": path, "state": state, "reason": "source-refused"}, None

        def forbidden(path: Path) -> PythonAstSnapshot:
            raise AssertionError("source refusal must prevent AST byte reads")

        monkeypatch.setattr(repository.source, "member", member)
        monkeypatch.setattr(task_evidence_source_context, "read_python_ast", forbidden)
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    assert "source_observation" not in json.dumps(_logical(packet))


@pytest.mark.parametrize(
    "transport", ["cli", pytest.param("mcp", marks=pytest.mark.host_mcp_sdk)]
)
def test_initial_source_context_survives_real_transports(
    tmp_path: Path, transport: str
) -> None:
    from scripts.repository_evaluation.backend_matrix import INITIAL_TOKEN_CEILING
    from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp

    _write(tmp_path)
    state = tmp_path / ".hashmarks"
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        expected = _source(repository.tasks.evidence(TASK, result_mode="initial"))
    capture = capture_cli if transport == "cli" else capture_mcp
    rows = capture(
        tmp_path,
        state,
        {
            "operation": "task_evidence",
            "inputs": {"task": TASK, "result_mode": "initial"},
        },
    )
    assert len(rows) == len(FORMATS)
    for row in rows:
        response = assert_object(row["response"])
        assert _source(assert_object(response.get("result", response))) == expected
        if row["format"] != "none":
            assert GUARD in json.dumps(response["presentation"])
        if row["format"] in {"compact", "text"}:
            assert row["estimated_tokens"] <= INITIAL_TOKEN_CEILING


def test_compact_source_qualifiers_preserve_missing_and_json_distinct_values(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = decode_initial_packet(
            repository.tasks.evidence(TASK, result_mode="initial")
        )
    source = _source(packet)
    original_anchor = deepcopy(assert_records(source["line_anchors"])[0])
    anchors = []
    for index, value in enumerate([False, 0, 0.0, None]):
        anchor = deepcopy(original_anchor)
        anchor["line"] = index + 10
        anchor["future_value"] = value
        if index != 3:
            anchor["optional_value"] = None
        context = assert_records(anchor["context_excerpt"])
        for ordinal, row in enumerate(context):
            row["future_value"] = [False, 0, None][ordinal % 3]
            if ordinal:
                row["optional_value"] = None
        anchors.append(anchor)
    source["line_anchors"] = anchors
    source["future_source_qualification"] = {"unknown": None, "zero": 0.0}
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = encode_initial_packet(packet)
    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="compact"
    )
    projection = assert_object(response["presentation"])
    group = next(
        row for row in assert_records(projection["groups"]) if row["family"] == "source"
    )
    finding = assert_records(group["findings"])[0]
    details = deepcopy(assert_object(finding["details"]))
    shared = assert_object(details.pop("line_anchor_qualifiers"))
    assert "future_value" not in shared
    assert "optional_value" not in shared
    restored = []
    for raw_anchor in assert_records(details["line_anchors"]):
        anchor = {**shared, **raw_anchor}
        context_shared = assert_object(anchor.pop("context_excerpt_qualifiers", {}))
        anchor["context_excerpt"] = [
            {**context_shared, **row}
            for row in assert_records(anchor["context_excerpt"])
        ]
        restored.append(anchor)
    assert json.dumps(restored, sort_keys=True) == json.dumps(anchors, sort_keys=True)
    assert len(json.dumps(finding["details"])) < len(
        json.dumps({**details, "line_anchors": anchors})
    )
    assert not any(
        row["source_ref"] == assert_array(finding["source_refs"])[0]
        for row in assert_records(projection["source_context"])
    )
    assert decode_initial_packet(assert_object(response["result"])) == packet
    assert decode_initial_packet(wire) == packet
