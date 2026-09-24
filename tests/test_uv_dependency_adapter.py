from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap.engine import CodeMap


def _lock(version: str = "1.0.0") -> bytes:
    return f'''version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dummy-app"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [
    {{ name = "dummy-dep" }},
]

[package.metadata]
requires-dist = [{{ name = "dummy-dep", directory = "vendor/dummy_dep" }}]

[[package]]
name = "dummy-dep"
version = "{version}"
source = {{ directory = "vendor/dummy_dep" }}
'''.encode()


def test_uv_lock_adapter_preserves_selection_source_and_factual_delta(
    tmp_path: Path,
) -> None:
    before_raw = uv_lock_dependency_observation(lock=_lock("1.0.0"))
    after_raw = uv_lock_dependency_observation(lock=_lock("2.0.0"))

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    before_dep = next(
        row for row in before["selections"] if row["component_id"] == "dummy-dep"
    )
    after_dep = next(
        row for row in after["selections"] if row["component_id"] == "dummy-dep"
    )
    assert before_dep["version"] == "1.0.0"
    assert after_dep["version"] == "2.0.0"
    assert before_dep["source"] == '{"directory":"vendor/dummy_dep"}'
    assert after_dep["source"] == before_dep["source"]
    assert delta["selections_added"] == [after_dep["node_id"]]
    assert delta["selections_removed"] == [before_dep["node_id"]]
    assert delta["causation"] == "not-inferred"


def test_uv_lock_adapter_preserves_relationship_and_inventory_change(
    tmp_path: Path,
) -> None:
    before_raw = uv_lock_dependency_observation(lock=_lock("1.0.0"))
    after_raw = uv_lock_dependency_observation(lock=_lock("2.0.0"))

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert len(delta["inventory_added"]) == 1
    assert len(delta["inventory_removed"]) == 1
    assert len(delta["relationships_added"]) == 1
    assert len(delta["relationships_removed"]) == 1


def test_uv_lock_adapter_does_not_promote_declared_metadata_to_resolution() -> None:
    raw = uv_lock_dependency_observation(lock=_lock())

    assert len(raw["relationships"]) == 1
    assert raw["relationships"][0]["kind"] == "dependency"
    assert raw["scope"]["evidence"] == "uv-lock"
    assert raw["module_ownership"] == []


def test_uv_lock_adapter_refuses_ambiguous_name_only_dependency() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "app"
version = "1"
source = { virtual = "." }
dependencies = [{ name = "shared" }]

[[package]]
name = "shared"
version = "1"
source = { registry = "https://example.invalid/simple" }

[[package]]
name = "shared"
version = "2"
source = { directory = "vendor/shared" }
"""
    with pytest.raises(ValueError, match="must resolve uniquely"):
        uv_lock_dependency_observation(lock=lock)


@pytest.mark.parametrize("source_key", ["virtual", "editable", "directory"])
def test_uv_lock_adapter_accepts_local_project_root_source_forms(
    source_key: str,
) -> None:
    lock = f"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "app"
version = "0.1.0"
source = {{ {source_key} = "." }}
dependencies = [{{ name = "dep" }}]

[[package]]
name = "dep"
version = "1.0.0"
source = {{ registry = "https://example.invalid/simple" }}
""".encode()

    raw = uv_lock_dependency_observation(lock=lock)

    assert len(raw["roots"]) == 1
    root_id = raw["roots"][0]["node_id"]
    assert root_id.startswith("app:0.1.0@")
    assert {row["node_id"] for row in raw["inventory"]} == {
        next(
            row["node_id"] for row in raw["selections"] if row["component_id"] == "dep"
        )
    }
