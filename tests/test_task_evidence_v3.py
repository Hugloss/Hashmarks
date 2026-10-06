from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_task_evidence_v3_separates_retrieval_ownership_and_freshness(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/owner.py",
        "def target_impl(value: int) -> int:\n    return value + 1\n",
    )
    _write(
        tmp_path,
        "tests/test_owner.py",
        "from src.owner import target_impl\n\n"
        "def test_target_impl():\n"
        "    assert target_impl(1) == 2\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("change target_impl behavior", token_budget=256)

    assert packet["schema"] == "hashmarks.task-evidence.v3"
    assert "status" not in packet
    assert packet["retrieval"]["ownership_authority"] is False
    assert packet["ownership"]["status"] == "resolved"
    assert packet["ownership"]["owner"]["path"] == "src/owner.py"
    assert packet["ownership"]["basis"] in {"unique-exact-symbol", "exact-symbol"}
    assert packet["ownership"]["authority"] == "repository-ownership-only"
    assert packet["verification"]["selected"]["path"] == "tests/test_owner.py"
    assert packet["freshness"]["state"] in {"unknown", "current", "stale"}
    assert packet["consumer_action"] == "external"


def test_task_evidence_v3_retrieval_is_compact_non_authoritative_projection(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/owner.py",
        "def target_impl(value: int) -> int:\n    return value + 1\n",
    )
    _write(
        tmp_path,
        "src/helper.py",
        "def helper(value: int) -> int:\n    return value\n",
    )
    task = "locate target_impl behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_evidence(task, limit=20, token_budget=256)

    retrieval = packet["retrieval"]
    assert retrieval["presentation"] == "compact-locators-v1"
    assert retrieval["ownership_authority"] is False
    assert retrieval["results"]
    projected = retrieval["results"][0]
    internal = action["canonical"][0]
    assert projected["path"] == internal["path"]
    assert projected["rank"] == 1
    assert projected.get("symbol") == (internal.get("qualname") or internal.get("name"))
    assert projected.get("roles") == internal.get("roles")
    assert projected.get("evidence_visibility") == internal.get("evidence_visibility")
    assert projected.get("start_line") == internal.get("start_line")
    assert projected.get("end_line") == internal.get("end_line")
    for internal_only in (
        "canonical_rank",
        "canonical_score",
        "domains",
        "name",
        "qualname",
        "signature",
    ):
        assert internal_only not in projected


def test_task_evidence_v3_consumes_canonical_admitted_edit(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/owner.py",
        "def target_impl(value: int) -> int:\n    return value + 1\n",
    )
    _write(
        tmp_path,
        "tests/test_owner.py",
        "from src.owner import target_impl\n\n"
        "def test_target_impl():\n"
        "    assert target_impl(1) == 2\n",
    )
    task = "change target_impl behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)
        assert action["ownership_authority"]["owner_resolved"] is True
        assert action["edit"]["path"] == "src/owner.py"
        assert action["admitted_edit"]["path"] == "src/owner.py"

        action["admitted_edit"] = None
        codemap.task_action_map = lambda *args, **kwargs: action  # type: ignore[method-assign]
        packet = codemap.task_evidence(task, token_budget=256)

    assert packet["ownership"]["candidate"]["path"] == "src/owner.py"
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["basis"] is None
    assert packet["explicit_target"]["path"] == "src/owner.py"


def test_task_evidence_v3_keeps_ambiguity_independent_from_freshness(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def calculate_value():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def calculate_value():\n    return 2\n")

    task = "fix calculate_value"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)
        packet = codemap.task_evidence(task, token_budget=256)

    ownership = packet["ownership"]
    assert ownership["status"] == "ambiguous"
    assert ownership["owner"] is None
    assert ownership["ambiguity"]["ambiguous"] is True
    assert ownership["source_evidence"] is None
    assert (
        ownership["authority_proof_identity"]
        == action["ownership_authority"]["authority_proof_identity"]
    )
    next_read = ownership["next_read"]
    assert next_read["path"] in {"src/a.py", "src/b.py"}
    assert str(next_read["symbol"]).endswith("calculate_value")
    assert next_read["start_line"] == 1
    assert next_read["end_line"] == 2
    assert next_read["reason"] == "ownership-ambiguity-discrimination"
    assert next_read["ambiguity_reason"]
    assert next_read["authority"] == "non-authoritative-discrimination"
    assert next_read["discriminator"]
    assert packet["freshness"]["state"] in {"unknown", "current", "stale"}


def test_task_evidence_v3_owner_is_invariant_to_bounded_retrieval(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/runtime/executor_pool.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )
    for index in range(8):
        _write(
            tmp_path,
            f"frontend/src/client_{index}.ts",
            "export function cancelQueuedAdmission(expected_sequence: number) {\n"
            "  return { action: 'cancel_queued_admission', expected_sequence };\n"
            "}\n"
            "// cancel_queued_admission expected_sequence consumer\n",
        )

    task = "cancel_queued_admission expected_sequence"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        narrow = codemap.task_evidence(task, limit=1, per_role=1, token_budget=256)
        wide = codemap.task_evidence(task, limit=20, per_role=3, token_budget=256)

    assert narrow["ownership"]["status"] == "resolved"
    assert wide["ownership"]["status"] == "resolved"
    assert narrow["ownership"]["owner"]["path"] == "backend/runtime/executor_pool.py"
    assert wide["ownership"]["owner"]["path"] == "backend/runtime/executor_pool.py"
    assert narrow["ownership"]["basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert wide["ownership"]["basis"] in {"exact-symbol", "unique-exact-symbol"}


def test_task_evidence_v3_keeps_dependency_as_related_evidence_not_owner(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/publish.py", "def publish_result(value):\n    return value\n")
    _write(
        tmp_path,
        "src/authority.py",
        "class AuthorityReceipt:\n"
        "    def canonical_identity(self):\n"
        "        return 'canonical'\n",
    )
    task = "Fix publish_result so it uses AuthorityReceipt.canonical_identity"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_evidence(task, limit=20, token_budget=256)

    assert packet["ownership"]["status"] == "resolved"
    assert packet["ownership"]["owner"]["path"] == "src/publish.py"
    assert packet["ownership"]["candidate"]["path"] == "src/publish.py"
    assert packet["explicit_target"]["path"] == "src/publish.py"
    assert packet["ownership"]["ambiguity"]["ambiguous"] is False

    retrieval_paths = {row["path"] for row in packet["retrieval"]["results"]}
    canonical_paths = {row["path"] for row in action["canonical"]}
    assert "src/authority.py" in canonical_paths
    assert "src/authority.py" in retrieval_paths
    assert packet["related"]["candidates"] == action["related"]


def test_natural_language_prefix_path_owner_does_not_drift_to_query_neighbor(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "hashmarks/codemap/repository_index_store.py",
        "class WorkspaceMapStore:\n"
        "    def paths_under(self, prefix: str) -> list[str]:\n"
        "        return [path for path in self.paths if path.startswith(prefix)]\n",
    )
    _write(
        tmp_path,
        "hashmarks/codemap/store_queries.py",
        "def query_paths_for_prefix(store, prefix: str) -> list[str]:\n"
        "    return store.paths_under(prefix)\n",
    )
    _write(
        tmp_path,
        "tests/test_store.py",
        "from hashmarks.codemap.repository_index_store import WorkspaceMapStore\n"
        "# verifies indexed repository paths under a requested prefix\n",
    )

    task = (
        "Change the behavior that enumerates indexed repository paths underneath "
        "a requested prefix."
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20, per_role=3)

    assert action["ambiguity"]["ambiguous"] is False
    assert action["edit"]["path"] == "hashmarks/codemap/repository_index_store.py"
    assert action["edit"]["qualname"].endswith("WorkspaceMapStore.paths_under")


def test_behavioral_test_shaped_source_requires_production_reference(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/test_support.py",
        "def runtime_probe_state():\n    return 'ready'\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change the behavior that reports runtime probe state."
        )

    assert action["edit"] is None
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ownership_authority"]["owner_resolved"] is False


def test_behavioral_owner_discovery_stays_on_semantic_owner(tmp_path: Path) -> None:
    cases = [
        (
            "stale",
            "Change the behavior that removes stale indexed paths during a full CodeMap sync.",
            "hashmarks/codemap/indexing_lifecycle.py",
            {
                "hashmarks/codemap/indexing_lifecycle.py": (
                    "def _sync_remove_stale_paths(store, live_paths):\n"
                    "    stale = store.paths() - live_paths\n"
                    "    return store.delete_paths(stale)\n"
                ),
                "hashmarks/codemap/service.py": (
                    "from hashmarks.codemap.indexing_lifecycle import _sync_remove_stale_paths\n"
                    "def full_sync(store, live_paths):\n"
                    "    return _sync_remove_stale_paths(store, live_paths)\n"
                ),
            },
        ),
        (
            "prune",
            "Change the behavior that prunes directory names before repository file discovery descends into them.",
            "hashmarks/codemap/repository_file_discovery.py",
            {
                "hashmarks/codemap/repository_file_discovery.py": (
                    "def _prune_discovery_dirs(names):\n"
                    "    names[:] = [name for name in names if not name.startswith('.')]\n"
                ),
                "hashmarks/codemap/service.py": (
                    "from hashmarks.codemap.repository_file_discovery import _prune_discovery_dirs\n"
                    "def discover(names):\n"
                    "    _prune_discovery_dirs(names)\n"
                ),
            },
        ),
        (
            "mcp",
            "Change the MCP surface behavior that returns task evidence to a consumer.",
            "hashmarks/mcp_surface.py",
            {
                "hashmarks/mcp_surface.py": (
                    "class HashmarksMcpSurface:\n"
                    "    def task_evidence(self, task):\n"
                    "        return {'task': task}\n"
                ),
                "hashmarks/mcp_server.py": (
                    "from hashmarks.mcp_surface import HashmarksMcpSurface\n"
                    "def serve_task(surface: HashmarksMcpSurface, task):\n"
                    "    return surface.task_evidence(task)\n"
                ),
            },
        ),
        (
            "identity",
            (
                "Change the function used by the test-selection work-selection "
                "envelope and its repository-binding validation to compute "
                "extraction-stable repository content identity from repository bytes."
            ),
            "hashmarks/test_shards.py",
            {
                "hashmarks/test_shards.py": (
                    "def repository_content_identity(root):\n"
                    "    return 'content-bytes'\n\n"
                    "def work_selection_envelope(root):\n"
                    "    return {'repository': repository_content_identity(root)}\n\n"
                    "def validate_work_selection_repository_binding(root, expected):\n"
                    "    return repository_content_identity(root) == expected\n"
                ),
                "hashmarks/engine.py": (
                    "class IdentityEngine:\n"
                    "    def repository_identity(self, root):\n"
                    "        return 'merkle-identity'\n"
                ),
                "scripts/repository_probe.py": (
                    "from hashmarks.test_shards import repository_content_identity\n"
                    "def observe_repository(root):\n"
                    "    return repository_content_identity(root)\n"
                ),
            },
        ),
    ]

    for case_id, task, expected_path, files in cases:
        root = tmp_path / case_id
        root.mkdir()
        for rel, content in files.items():
            _write(root, rel, content)
        with CodeMap(root) as codemap:
            codemap.sync()
            action = codemap.task_action_map(task, limit=20, per_role=3)
        assert action["ambiguity"]["ambiguous"] is False, case_id
        assert action["edit"]["path"] == expected_path, case_id


def test_task_evidence_projects_same_authority_proof_across_bounds(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/owner.py", "def unique_owner(value):\n    return value\n")
    task = "Refactor owner.unique_owner without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=1, per_role=1)
        narrow = codemap.task_evidence(task, limit=1, per_role=1, token_budget=64)
        wide = codemap.task_evidence(task, limit=20, per_role=3, token_budget=256)

    proof = action["ownership_authority"]["authority_proof_identity"]
    assert narrow["ownership"]["authority_proof_identity"] == proof
    assert wide["ownership"]["authority_proof_identity"] == proof
    assert narrow["ownership"]["owner"]["path"] == "src/owner.py"
    assert wide["ownership"]["owner"]["path"] == "src/owner.py"
    assert narrow["ownership"]["proof_scope_complete"] is True
    assert wide["ownership"]["proof_scope_complete"] is True


def test_task_evidence_preserves_dense_natural_language_owner_candidates(
    tmp_path: Path,
) -> None:
    cases = (
        (
            "prefix",
            (
                "Without editing files, identify the single function that enumerates "
                "indexed repository paths underneath a requested prefix."
            ),
            "hashmarks/codemap/repository_index_store.py",
            "paths_under",
            (
                "class WorkspaceMapStore:\n"
                "    def paths_under(self, prefix: str) -> list[str]:\n"
                "        return [path for path in self.paths if path.startswith(prefix)]\n"
            ),
            (
                "def enumerate_indexed_repository_paths_{index}():\n"
                "    # indexed repository paths requested by repository callers\n"
                "    return []\n"
            ),
        ),
        (
            "prune",
            (
                "Without editing files, identify the function that prunes directory "
                "names before repository file discovery descends into them."
            ),
            "hashmarks/codemap/repository_file_discovery.py",
            "_prune_discovery_dirs",
            (
                "def _prune_discovery_dirs(names: list[str]) -> None:\n"
                "    names[:] = [name for name in names if not name.startswith('.')]\n"
            ),
            (
                "def repository_file_discovery_{index}(names):\n"
                "    # directory names repository file discovery descends here\n"
                "    return names\n"
            ),
        ),
        (
            "identity",
            (
                "Without editing files, identify the function used by the test-selection "
                "work-selection envelope and its repository-binding validation to compute "
                "the extraction-stable repository content identity from repository bytes."
            ),
            "hashmarks/test_shards.py",
            "repository_content_identity",
            (
                "def repository_content_identity(root):\n"
                "    return 'content-bytes'\n\n"
                "def work_selection_envelope(root):\n"
                "    return {'repository': repository_content_identity(root)}\n\n"
                "def validate_work_selection_repository_binding(root, expected):\n"
                "    return repository_content_identity(root) == expected\n"
            ),
            (
                "def repository_identity_{index}(value):\n"
                "    # repository content identity bytes validation\n"
                "    return value\n"
            ),
        ),
    )

    for (
        case_id,
        task,
        expected_path,
        expected_symbol,
        owner_source,
        decoy_source,
    ) in cases:
        root = tmp_path / case_id
        root.mkdir()
        _write(root, expected_path, owner_source)
        for index in range(32):
            _write(
                root,
                f"hashmarks/codemap/decoy_{index:02d}.py",
                decoy_source.format(index=index),
            )

        with CodeMap(root) as codemap:
            codemap.sync()
            for query in (
                task,
                task + " Return exactly one JSON object with keys path and symbol, "
                "and nothing else.",
            ):
                packet = codemap.task_evidence(query, limit=20, token_budget=256)
                retrieval = packet["retrieval"]["results"]
                assert any(
                    row["path"] == expected_path
                    and str(row.get("symbol") or "").rsplit(".", 1)[-1]
                    == expected_symbol
                    for row in retrieval
                ), (case_id, query)
                assert packet["retrieval"]["ownership_authority"] is False


def test_task_evidence_natural_supplements_respect_deny_visibility(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "hidden/engine.py",
        "def cobalt_owner() -> str:\n    return 'implementation-secret'\n",
    )
    _write(
        tmp_path,
        "src/route.py",
        "from hidden.engine import cobalt_owner\n\n"
        "def cobalt_route() -> str:\n    return cobalt_owner()\n",
    )
    _write(
        tmp_path,
        "tests/test_route.py",
        "from src.route import cobalt_route\n\n"
        "def test_cobalt_route():\n    assert cobalt_route() == 'new'\n",
    )
    _write(
        tmp_path,
        ".hashmarks-context.toml",
        '[[rule]]\npattern = "hidden/**"\nvisibility = "deny"\n',
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(
            "Change cobalt route behavior and verify it",
            limit=20,
            token_budget=256,
        )

    retrieval = packet["retrieval"]["results"]
    assert all(row.get("path") != "hidden/engine.py" for row in retrieval)
    assert all(
        str(row.get("symbol") or "").rsplit(".", 1)[-1] != "cobalt_owner"
        for row in retrieval
    )


def _dense_prefix_repository(root: Path) -> tuple[Path, str]:
    owner = root / "hashmarks/codemap/repository_index_store.py"
    _write(
        root,
        "hashmarks/codemap/repository_index_store.py",
        "class WorkspaceMapStore:\n"
        "    def paths_under(self, prefix: str) -> list[str]:\n"
        "        return [path for path in self.paths if path.startswith(prefix)]\n",
    )
    for index in range(32):
        _write(
            root,
            f"hashmarks/codemap/decoy_{index:02d}.py",
            f"def enumerate_indexed_repository_paths_{index}():\n"
            "    # indexed repository paths requested by repository callers\n"
            "    return []\n",
        )
    task = (
        "Without editing files, identify the single function that enumerates "
        "indexed repository paths underneath a requested prefix."
    )
    return owner, task


def test_task_evidence_v3_compact_retrieval_is_materially_smaller_than_internal_rows(
    tmp_path: Path,
) -> None:
    _owner, task = _dense_prefix_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=9)
        packet = codemap.task_evidence(task, limit=9, token_budget=256)

    internal = json.dumps(
        action["canonical"],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    projected = json.dumps(
        packet["retrieval"]["results"],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert len(packet["retrieval"]["results"]) == len(action["canonical"])
    assert len(projected) < len(internal) * 0.8


def test_task_evidence_supplements_account_for_displaced_canonical_hits(
    tmp_path: Path,
) -> None:
    owner, task = _dense_prefix_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_evidence(task, limit=20, token_budget=256)
        tight = codemap.task_evidence(task, limit=9, token_budget=256)
        delta = codemap.task_post_change_delta(
            task, [owner.relative_to(tmp_path)], previous_evidence=packet
        )

    retrieval = packet["retrieval"]
    results = retrieval["results"]
    supplements = [row for row in results if row.get("supplement")]
    assert retrieval["presentation"] == "compact-locators-v1"
    assert 1 <= len(supplements) <= 2
    assert len(results) <= 20
    canonical_prefix = results[: -len(supplements)]
    for rank, (projected, internal) in enumerate(
        zip(
            canonical_prefix,
            action["canonical"][: len(canonical_prefix)],
            strict=True,
        ),
        1,
    ):
        assert projected["path"] == internal["path"]
        assert projected["rank"] == rank
        assert projected.get("symbol") == (
            internal.get("qualname") or internal.get("name")
        )
        assert projected.get("roles") == internal.get("roles")
        assert projected.get("evidence_visibility") == internal.get(
            "evidence_visibility"
        )
        assert projected.get("start_line") == internal.get("start_line")
        assert projected.get("end_line") == internal.get("end_line")
        assert "signature" not in projected
        assert "canonical_score" not in projected
        assert "domains" not in projected
    assert retrieval["canonical_omitted_results"] == len(action["canonical"]) - len(
        canonical_prefix
    )
    assert retrieval["canonical_omitted_results"] > 0
    assert retrieval["supplemental_results"] == len(supplements)
    assert retrieval["supplemental_authority"] is False
    assert retrieval["ordering"] == "canonical-then-bounded-natural-language"
    assert any(
        str(row.get("symbol") or "").rsplit(".", 1)[-1] == "paths_under"
        for row in supplements
    )
    assert all(row["supplement"] == "bounded-natural-language" for row in supplements)
    assert all(row["evidence_visibility"] == "source" for row in supplements)
    assert all(not row.get("supplement") for row in tight["retrieval"]["results"])
    assert "canonical_omitted_results" not in tight["retrieval"]
    assert packet["ownership"]["candidate"]["path"] == action["edit"]["path"]
    assert delta["schema"] == "hashmarks.task-post-change-delta.v2"


@pytest.mark.parametrize("mutation", ("rewrite", "delete"))
def test_task_evidence_supplement_excludes_unsignaled_stale_symbol(
    tmp_path: Path,
    mutation: str,
) -> None:
    owner, task = _dense_prefix_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_evidence(task, limit=20, token_budget=256)
        assert any(
            row.get("supplement")
            and str(row.get("symbol") or "").rsplit(".", 1)[-1] == "paths_under"
            for row in before["retrieval"]["results"]
        )
        if mutation == "rewrite":
            owner.write_text(
                "class WorkspaceMapStore:\n"
                "    def unrelated(self):\n"
                "        return 0\n",
                encoding="utf-8",
            )
        else:
            owner.unlink()
        after = codemap.task_evidence(task, limit=20, token_budget=256)

    assert all(
        str(row.get("symbol") or "").rsplit(".", 1)[-1] != "paths_under"
        for row in after["retrieval"]["results"]
    )


def test_task_evidence_supplement_preserves_outline_visibility(
    tmp_path: Path,
) -> None:
    owner, task = _dense_prefix_repository(tmp_path)
    _write(
        tmp_path,
        ".hashmarks-context.toml",
        '[[rule]]\npattern = "hashmarks/codemap/repository_index_store.py"\n'
        'visibility = "outline"\n',
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(task, limit=20, token_budget=256)

    supplements = [
        row
        for row in packet["retrieval"]["results"]
        if row.get("supplement")
        and row["path"] == owner.relative_to(tmp_path).as_posix()
    ]
    assert supplements
    assert all(row["evidence_visibility"] == "outline" for row in supplements)
