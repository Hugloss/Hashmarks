from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_exact_qualified_identifier_is_not_displaced_by_test_structural_walk(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/repository_index_store.py",
        "class WorkspaceMapStore:\n    def paths_under(self):\n        return []\n",
    )
    _write(
        tmp_path,
        "pkg/indexing_lifecycle.py",
        "def _sorted_paths_under():\n    return []\n",
    )
    _write(
        tmp_path, "pkg/service.py", "def default_codemap_socket():\n    return 'sock'\n"
    )
    _write(tmp_path, "pkg/__init__.py", "from .service import default_codemap_socket\n")
    _write(
        tmp_path,
        "tests/test_store_queries.py",
        "from pkg import default_codemap_socket\n\n"
        "def test_paths_under_contract():\n"
        "    # WorkspaceMapStore.paths_under\n"
        "    assert default_codemap_socket()\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize WorkspaceMapStore.paths_under")

    assert action["edit"]["path"] == "pkg/repository_index_store.py"
    assert action["edit"]["qualname"] == "WorkspaceMapStore.paths_under"
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_resolution"] is None


def test_exact_method_identifier_is_not_displaced_by_import_continuation(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/indexing_lifecycle.py",
        "from .repository_index_store import WorkspaceMapStore\n\n"
        "class IndexingLifecycleMixin:\n"
        "    def _sync_remove_stale_paths(self):\n"
        "        return WorkspaceMapStore()\n",
    )
    _write(
        tmp_path,
        "pkg/repository_index_store.py",
        "from .store_queries import WorkspaceMapQueryMixin\n\n"
        "class WorkspaceMapStore(WorkspaceMapQueryMixin):\n"
        "    pass\n",
    )
    _write(
        tmp_path, "pkg/store_queries.py", "class WorkspaceMapQueryMixin:\n    pass\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize _sync_remove_stale_paths")

    assert action["edit"]["path"] == "pkg/indexing_lifecycle.py"
    assert (
        action["edit"]["qualname"] == "IndexingLifecycleMixin._sync_remove_stale_paths"
    )
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_resolution"] is None


def test_duplicate_exact_identifiers_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.py", "def calculate_value():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def calculate_value():\n    return 2\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize calculate_value")

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_generic_task_keeps_structural_owner_resolution(tmp_path: Path) -> None:
    _write(tmp_path, "src/__init__.py", "")
    _write(tmp_path, "src/case/__init__.py", "")
    _write(
        tmp_path,
        "src/case/engine.py",
        "def apply_case(value: str) -> str:\n    return value + '-active'\n",
    )
    _write(
        tmp_path,
        "src/case/route.py",
        "from .engine import apply_case\n\n"
        "def handle_ember(value: str) -> str:\n"
        "    return apply_case(value)\n",
    )
    _write(
        tmp_path,
        "tests/case/test_behavior.py",
        "from src.case.route import handle_ember\n\n"
        "def test_ember_contract():\n"
        "    assert handle_ember('x') == 'x-active'\n",
    )
    _write(
        tmp_path, "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix ember accepted response behavior owner")

    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["ownership_resolution"]["path"] == "src/case/engine.py"
    assert action["ambiguity"]["ambiguous"] is False


def test_exact_verification_symbol_does_not_become_edit_authority(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/__init__.py", "")
    _write(tmp_path, "src/worker.py", "def run_task():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_worker.py",
        "from src.worker import run_task\n\n"
        "def test_run_task_contract():\n"
        "    assert run_task() == 1\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix test_run_task_contract behavior")

    assert action["edit"]["path"] == "src/worker.py"
    assert action["edit"]["path"] != "tests/test_worker.py"
    assert action["ambiguity"]["ambiguous"] is False


def test_literal_path_remains_authoritative_without_structural_displacement(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/worker.py", "def run_task():\n    return 1\n")
    _write(tmp_path, "src/wrapper.py", "from .worker import run_task\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize src/worker.py")

    assert action["edit"]["path"] == "src/worker.py"
    assert action["ownership_resolution"] is None
    assert action["ambiguity"]["ambiguous"] is False


def test_reexport_with_duplicate_exact_source_owners_stays_ambiguous(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/__init__.py", "from .a import resolve_target\n")
    _write(tmp_path, "src/a.py", "def resolve_target():\n    return 'a'\n")
    _write(tmp_path, "src/b.py", "def resolve_target():\n    return 'b'\n")
    _write(
        tmp_path,
        "tests/test_api.py",
        "from src import resolve_target\n\n"
        "def test_api():\n"
        "    assert resolve_target()\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize resolve_target")

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_comment_only_lexical_match_cannot_override_active_exact_symbol(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/live.py", "def active_target():\n    return 1\n")
    _write(
        tmp_path,
        "src/dead.py",
        "# active_target old implementation removed\nVALUE = 2\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("optimize active_target")

    assert action["edit"]["path"] == "src/live.py"
    assert action["edit"]["qualname"] == "active_target"
    assert action["ambiguity"]["ambiguous"] is False


def test_test_shaped_source_without_production_import_stays_verification_only(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/test_support.py", "def runtime_probe():\n    return 1\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix runtime_probe")

    assert action["edit"] is None
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "no-edit-candidate"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_test_shaped_source_can_recover_edit_authority_from_exact_production_import(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/test_support.py", "def runtime_probe():\n    return 1\n")
    _write(
        tmp_path,
        "pkg/consumer.py",
        "from .test_support import runtime_probe\n\ndef use_probe():\n    return runtime_probe()\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix runtime_probe")

    assert action["edit"]["path"] == "pkg/test_support.py"
    assert action["edit"]["qualname"] == "runtime_probe"
    assert action["edit"]["reference_backed_source_projection"] is True
    assert action["edit"]["reference_backed_source_path"] == "pkg/consumer.py"
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_unqualified_duplicate_plain_method_name_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.py", "class A:\n    def resolve(self):\n        return 1\n")
    _write(tmp_path, "src/b.py", "class B:\n    def resolve(self):\n        return 2\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix resolve")

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_literal_path_constrains_exact_method_within_that_file(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/store.py",
        "class Store:\n    def paths_under(self):\n        return []\n",
    )
    _write(
        tmp_path,
        "src/other.py",
        "class Other:\n    def paths_under(self):\n        return ['other']\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix src/store.py Store.paths_under")

    assert action["edit"]["path"] == "src/store.py"
    assert action["edit"]["qualname"] == "Store.paths_under"
    assert action["edit"]["exact_identifier_projection"] is True
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_unique_exact_callable_can_discriminate_competing_verification_rows(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/generic.py", "def target_impl():\n    return 1\n")
    for index in range(4):
        _write(
            tmp_path,
            f"tests/test_target_impl_{index}.py",
            f"def test_target_impl_{index}():\n"
            "    # target_impl verification\n"
            "    assert True\n",
        )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix target_impl verification behavior")

    assert action["edit"]["path"] == "src/generic.py"
    assert action["edit"]["qualname"] == "target_impl"
    assert action["edit"]["canonical_rank"] > 2
    assert action["edit"]["exact_identifier_projection"] is True
    assert action["ownership_resolution"] is None
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_strong_plain_identifier_recovers_exact_owner_from_index(
    tmp_path: Path,
) -> None:
    """Oh-Goon dogfood: bounded retrieval must not hide an exact mutation owner."""
    _write(
        tmp_path,
        "backend/runtime/executor_pool.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )
    _write(
        tmp_path,
        "frontend/src/createApiClient.ts",
        "export function cancelQueuedAdmission(expected_sequence: number) {\n"
        "  return { action: 'cancel_queued_admission', expected_sequence };\n"
        "}\n"
        "// cancel_queued_admission expected_sequence consumer surface\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        candidates = codemap._task_action_plain_identifier_index_candidates(
            {"cancel_queued_admission"},
            set(),
            canonical_rank=2,
        )

    assert len(candidates) == 1
    assert candidates[0]["path"] == "backend/runtime/executor_pool.py"
    assert candidates[0]["name"] == "cancel_queued_admission"
    assert candidates[0]["exact_identifier_projection"] is True
    assert candidates[0]["plain_identifier_index_projection"] is True


def test_plain_identifier_index_does_not_promote_verification_symbol(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/worker.py", "def run_task():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_worker.py",
        "from src.worker import run_task\n\n"
        "def test_run_task_contract():\n"
        "    assert run_task() == 1\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        candidates = codemap._task_action_plain_identifier_index_candidates(
            {"test_run_task_contract"},
            set(),
            canonical_rank=2,
        )

    assert candidates == []


def test_plain_identifier_index_keeps_test_shaped_source_fail_closed_without_import_proof(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/test_support.py", "def runtime_probe():\n    return 1\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        candidates = codemap._task_action_plain_identifier_index_candidates(
            {"runtime_probe"},
            set(),
            canonical_rank=2,
        )

    assert candidates == []


def test_plain_identifier_index_preserves_duplicate_owner_ambiguity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def cancel_queued_admission():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def cancel_queued_admission():\n    return 2\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        candidates = codemap._task_action_plain_identifier_index_candidates(
            {"cancel_queued_admission"},
            set(),
            canonical_rank=2,
        )
        action = codemap.task_action_map("fix cancel_queued_admission", limit=1)

    assert {row["path"] for row in candidates} == {"src/a.py", "src/b.py"}
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False
