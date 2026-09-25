from __future__ import annotations

import tomllib
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


def test_uv_lock_adapter_uses_one_multi_authority_physical_source() -> None:
    raw = uv_lock_dependency_observation(lock=_lock())

    assert raw["evidence_sources"] == [
        {
            "source_id": "uv:lock",
            "kind": "uv-lock",
            "authorities": [
                "resolution-graph",
                "resolved-inventory",
                "selection",
            ],
            "context": "lock",
            "completeness": "complete",
            "truncation": "complete",
            "producer_digest": raw["evidence_sources"][0]["producer_digest"],
        }
    ]
    assert {ref for row in raw["inventory"] for ref in row["evidence_sources"]} == {
        "uv:lock"
    }


def test_uv_lock_adapter_does_not_promote_declared_metadata_to_resolution() -> None:
    raw = uv_lock_dependency_observation(lock=_lock())

    assert len(raw["relationships"]) == 1
    assert raw["relationships"][0]["kind"] == "dependency"
    assert raw["scope"] == {"requires_python": ">=3.11"}
    assert raw["module_ownership"] == []


def test_uv_lock_adapter_includes_every_committed_lock_dependency_group(
    tmp_path: Path,
) -> None:
    lock = (Path(__file__).resolve().parents[1] / "uv.lock").read_bytes()
    document = tomllib.loads(lock.decode())
    expected = sum(
        len(package.get("dependencies", []))
        + sum(len(rows) for rows in package.get("optional-dependencies", {}).values())
        + sum(len(rows) for rows in package.get("dev-dependencies", {}).values())
        for package in document["package"]
    )
    raw = uv_lock_dependency_observation(lock=lock)
    assert raw["producer"]["resolution_markers"] == document.get(
        "resolution-markers", []
    )
    assert len(raw["relationships"]) == expected
    assert len(raw["evidence_sources"]) == 1

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)
        root_id = next(
            row["node_id"]
            for row in observation["roots"]
            if row["node_id"].startswith("hashmarks:")
        )
        query = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "dependencies", "node_id": root_id, "context": "lock"}],
        )["results"][0]

    assert query["result"]
    assert {row["selection"]["component_id"] for row in query["result"]} >= {
        "mcp",
        "ruff",
    }
    assert {
        row["effective_scope"]
        for row in observation["relationships"]
        if row["source"] == root_id
    } >= {
        "extra:mcp",
        "dev:lint",
    }
    assert query["producer_authority"] == "caller-claimed"


@pytest.mark.parametrize(
    "group_section",
    [
        'optional-dependencies = "unsupported"',
        '[package.optional-dependencies]\nextra = "unsupported"',
        '[package.dev-dependencies]\ntest = "unsupported"',
    ],
)
def test_uv_lock_adapter_rejects_unsupported_group_shape(
    group_section: str,
) -> None:
    lock = f"""version = 1
revision = 3

[[package]]
name = "app"
version = "1"
source = {{ virtual = "." }}
{group_section}
""".encode()
    with pytest.raises(ValueError, match="must be a table|must be a list"):
        uv_lock_dependency_observation(lock=lock)


@pytest.mark.parametrize(
    ("dependency", "message"),
    [
        ('{ name = 123 }', "uv lock dependency name must be a string"),
        (
            '{ name = "dep", version = 1 }',
            "uv lock dependency version must be a string",
        ),
        (
            '{ name = "dep", marker = 123 }',
            "uv lock dependency marker must be a string",
        ),
    ],
)
def test_uv_lock_adapter_refuses_malformed_dependency_identity(
    dependency: str,
    message: str,
) -> None:
    lock = f"""version = 1
revision = 3

[[package]]
name = "app"
version = "1"
source = {{ virtual = "." }}
dependencies = [{dependency}]

[[package]]
name = "dep"
version = "1"
source = {{ registry = "https://example.invalid/simple" }}
""".encode()

    with pytest.raises(ValueError, match=message):
        uv_lock_dependency_observation(lock=lock)


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


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        (
            b"""version = true
revision = 3
[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
""",
            "unsupported uv lock schema version",
        ),
        (
            b"""version = 1
revision = true
[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
""",
            "uv lock revision must be a positive integer",
        ),
        (
            b"""version = 1
revision = 3
[[package]]
name = 123
version = "0.1.0"
source = { virtual = "." }
""",
            "uv lock package requires string name and version",
        ),
        (
            b"""version = 1
revision = 3
[[package]]
name = "demo"
version = 1
source = { virtual = "." }
""",
            "uv lock package requires string name and version",
        ),
    ],
)
def test_uv_lock_adapter_refuses_malformed_identity_fields(
    lock: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        uv_lock_dependency_observation(lock=lock)


def test_uv_lock_adapter_refuses_unknown_lock_schema_version() -> None:
    lock = b"""version = 2
revision = 0
requires-python = ">=3.11"

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""

    with pytest.raises(ValueError, match="unsupported uv lock schema version: 2"):
        uv_lock_dependency_observation(lock=lock)


def test_uv_lock_adapter_preserves_top_level_resolution_markers() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"
resolution-markers = [
    "python_full_version >= '3.12'",
    "python_full_version < '3.12'",
]

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""

    raw = uv_lock_dependency_observation(lock=lock)

    assert raw["producer"]["resolution_markers"] == [
        "python_full_version >= '3.12'",
        "python_full_version < '3.12'",
    ]


def test_uv_lock_adapter_binds_environment_domain_to_semantic_scope(
    tmp_path: Path,
) -> None:
    base = """version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""
    constrained = """version = 1
revision = 3
requires-python = ">=3.11"
supported-markers = ["sys_platform == 'linux'"]
required-markers = ["platform_machine == 'x86_64' and sys_platform == 'linux'"]

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            uv_lock_dependency_observation(lock=base.encode())
        )
        after = codemap.dependency_resolution_evidence(
            uv_lock_dependency_observation(lock=constrained.encode())
        )
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["scope"] == {"requires_python": ">=3.11"}
    assert after["scope"] == {
        "requires_python": ">=3.11",
        "required_environments": [
            "platform_machine == 'x86_64' and sys_platform == 'linux'"
        ],
        "supported_environments": ["sys_platform == 'linux'"],
    }
    assert before["definition_identity"] != after["definition_identity"]
    assert delta["comparability"] == "not-comparable"
    assert delta["reason"] == "definition-changed"


def test_uv_top_level_resolution_markers_are_observation_only(
    tmp_path: Path,
) -> None:
    before_lock = b"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""
    after_lock = b"""version = 1
revision = 3
requires-python = ">=3.11"
resolution-markers = ["python_full_version >= '3.12'"]

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            uv_lock_dependency_observation(lock=before_lock)
        )
        after = codemap.dependency_resolution_evidence(
            uv_lock_dependency_observation(lock=after_lock)
        )
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["comparability"] == "comparable"


def test_uv_lock_adapter_refuses_package_resolution_forks() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"
resolution-markers = [
    "python_full_version >= '3.12'",
    "python_full_version < '3.12'",
]

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
resolution-markers = ["python_full_version >= '3.12'"]
"""

    with pytest.raises(ValueError, match="uv package resolution forks are not modeled"):
        uv_lock_dependency_observation(lock=lock)


def test_uv_lock_adapter_refuses_unmodeled_conflicts() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"
conflicts = [[
  { package = "demo", extra = "cpu" },
  { package = "demo", extra = "gpu" },
]]

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
"""

    with pytest.raises(ValueError, match="uv lock conflicts are not modeled"):
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


def test_uv_lock_adapter_refuses_ambiguous_local_source_identity() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "app"
version = "0.1.0"
source = { virtual = ".", directory = "." }
"""

    with pytest.raises(ValueError, match="ambiguous local source identity"):
        uv_lock_dependency_observation(lock=lock)


def test_uv_lock_adapter_refuses_to_infer_non_dot_workspace_root() -> None:
    lock = b"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "member"
version = "0.1.0"
source = { editable = "packages/member" }

[[package]]
name = "local-dependency"
version = "1.0.0"
source = { directory = "vendor/local-dependency" }
"""

    with pytest.raises(ValueError, match="workspace membership evidence is required"):
        uv_lock_dependency_observation(lock=lock)
