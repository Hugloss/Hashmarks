"""Decisive regressions for canonical ownership, alias proof and snapshot reuse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from benchmarks.diagnostic_correspondence import materialize_fixture
from hashmarks import CodeMap
from hashmarks.codemap import diagnostic_observation
from hashmarks.file_store import UnstableFileError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hashmarks import Digest


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    materialize_fixture(tmp_path / "repo")
    with CodeMap(
        tmp_path / "repo",
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        yield codemap


def _bindings() -> list[dict[str, object]]:
    return [
        {
            "binding_id": f"consumer-{n}",
            "evidence": [{"path": "app/service.py", "start_line": 3, "end_line": 4}],
        }
        for n in range(16)
    ]


def test_distinct_consumer_bindings_share_one_snapshot_but_no_mutable_output(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = repository.file_store.read_bytes_stable
    reads = 0

    def observed(path: str | Path, *, max_attempts: int = 3) -> tuple[bytes, Digest]:
        nonlocal reads
        reads += 1
        return original(path, max_attempts=max_attempts)

    monkeypatch.setattr(repository.file_store, "read_bytes_stable", observed)
    first: Any = repository.bindings.observe(_bindings(), include_relationships=False)
    assert reads == 1
    assert len(first["bindings"]) == 16
    assert len({row["binding_id"] for row in first["bindings"]}) == 16
    facts = [row["evidence"] for row in first["bindings"]]
    assert all(row == facts[0] for row in facts)
    first["bindings"][0]["evidence"][0]["member_revision"] = "consumer-change"
    assert first["bindings"][1]["evidence"][0]["member_revision"] != "consumer-change"
    source = repository.workspace / "app/service.py"
    source.write_bytes(b"\n" + source.read_bytes())
    repository.index.sync()
    after: Any = repository.bindings.observe(_bindings(), include_relationships=False)
    assert reads == 2
    assert after["bindings"][1]["evidence"] != first["bindings"][1]["evidence"]


def test_source_mutation_during_shared_snapshot_never_yields_a_clean_packet(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = repository.file_store.read_bytes_stable
    source = repository.workspace / "app/service.py"

    def edit_after_capture(
        path: str | Path, *, max_attempts: int = 3
    ) -> tuple[bytes, Digest]:
        result = original(path, max_attempts=max_attempts)
        source.write_bytes(b"\n" + source.read_bytes())
        return result

    monkeypatch.setattr(repository.file_store, "read_bytes_stable", edit_after_capture)
    with pytest.raises(UnstableFileError, match="binding source changed"):
        repository.bindings.observe(_bindings(), include_relationships=False)


@pytest.mark.parametrize(
    "source",
    [
        "from .config import load_config as read_config\ndef handle_request(read_config):\n    return read_config()\n",
        "from .config import load_config as read_config\ndef handle_request():\n    read_config = lambda: 1\n    return read_config()\n",
        "from .config import load_config as read_config\nfrom .unrelated import handle_request as read_config\ndef handle_request():\n    return read_config()\n",
        "from .missing import load_config as read_config\ndef handle_request():\n    return read_config()\n",
    ],
)
def test_alias_spelling_never_overrides_shadowing_ambiguity_or_missing_import(
    repository: CodeMap, source: str
) -> None:
    (repository.workspace / "app/service.py").write_text(source, encoding="utf-8")
    repository.index.sync()
    packet: Any = repository.structure.locality("app/service.py::handle_request")
    assert {row["symbol_id"] for row in packet["nodes"]} == {
        "app/service.py::handle_request"
    }
    assert all(row["resolved_symbol_id"] is None for row in packet["edges"])


def test_public_diagnostic_operations_bind_the_canonical_producers() -> None:
    assert (
        CodeMap.external_diagnostic_observation
        is diagnostic_observation.external_diagnostic_observation
    )
    assert (
        CodeMap.diagnostic_observation_delta
        is diagnostic_observation.diagnostic_observation_delta
    )


@pytest.mark.parametrize(
    ("facade", "expected"),
    [
        ("from .config import load_config as renamed\n", "app/config.py::load_config"),
        (
            "def renamed():\n    return 0\nfrom .config import load_config as renamed\n",
            "app/config.py::load_config",
        ),
        ("def renamed():\n    return 0\nrenamed = 1\n", None),
        ("from .bridge import renamed\n", "app/config.py::load_config"),
        ("from .facade import renamed\n", None),
    ],
)
def test_reexport_walk_uses_final_declaration_identity(
    repository: CodeMap, facade: str, expected: str | None
) -> None:
    (repository.workspace / "app/facade.py").write_text(facade, encoding="utf-8")
    (repository.workspace / "app/bridge.py").write_text(
        "from .config import load_config as renamed\n", encoding="utf-8"
    )
    (repository.workspace / "app/service.py").write_text(
        "from .facade import renamed as read_config\n"
        "def handle_request():\n    return read_config()\n",
        encoding="utf-8",
    )
    repository.index.sync()
    packet: Any = repository.structure.locality("app/service.py::handle_request")
    targets = {row["resolved_symbol_id"] for row in packet["edges"]}
    assert targets == {expected}


def test_hidden_intermediate_facade_cannot_prove_an_exact_call(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    materialize_fixture(root)
    (root / "app/facade.py").write_text(
        "from .config import load_config as renamed\n", encoding="utf-8"
    )
    (root / "app/service.py").write_text(
        "from .facade import renamed as read_config\n"
        "def handle_request():\n    return read_config()\n",
        encoding="utf-8",
    )
    (root / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "app/facade.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structure.locality("app/service.py::handle_request")
    assert all(row["resolved_symbol_id"] is None for row in packet["edges"])
