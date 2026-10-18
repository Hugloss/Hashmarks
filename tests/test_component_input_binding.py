"""Independent component construction cannot blend repository/read authorities."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.evidence_correlation import RepositoryCorrelation
from hashmarks.codemap.evidence_graph import RepositoryRelationships
from hashmarks.codemap.evidence_verification import RepositoryVerification
from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.ownership_graph import RepositoryOwnership
from hashmarks.codemap.repository_changes import RepositoryChanges
from hashmarks.codemap.repository_context import RepositoryContext
from hashmarks.codemap.repository_dependencies import RepositoryDependencies
from hashmarks.codemap.repository_intelligence_query import RepositoryViews
from hashmarks.codemap.repository_source import RepositorySource
from hashmarks.codemap.repository_tasks import RepositoryTasks
from hashmarks.codemap.structural_locality import RepositoryStructure


@pytest.fixture
def repositories(tmp_path: Path) -> Iterator[tuple[CodeMap, CodeMap]]:
    with ExitStack() as resources:
        selected: list[CodeMap] = []
        for label in ("left", "right"):
            workspace = tmp_path / label
            workspace.mkdir()
            (workspace / "owner.py").write_text(f"def owner(): return '{label}'\n")
            repository = resources.enter_context(
                CodeMap(
                    workspace,
                    state_dir=tmp_path / f"state-{label}",
                    artifact_db=tmp_path / "artifacts.sqlite3",
                )
            )
            repository.index.sync()
            selected.append(repository)
        yield selected[0], selected[1]


def _mixed_factories(left: CodeMap, right: CodeMap) -> dict[str, Callable[[], object]]:
    return {
        "source": lambda: RepositorySource(left.index, right.reads),
        "relationships": lambda: RepositoryRelationships(left._imports, right.native),
        "structure": lambda: RepositoryStructure(
            left.source, left._imports, left.native, right.relationships
        ),
        "context": lambda: RepositoryContext(
            left.source, left.search, right.relationships, left._context_cache
        ),
        "ownership": lambda: RepositoryOwnership(
            left.source, left._imports, right.structure, left.search
        ),
        "tasks": lambda: RepositoryTasks(
            left.search,
            left.ownership,
            right.verification,
            left.relationships,
            left.context,
        ),
        "dependencies": lambda: RepositoryDependencies(
            left.source, left._imports, right.correlation
        ),
        "changes": lambda: RepositoryChanges(left.tasks, right.relationships),
        "views-cross": lambda: RepositoryViews(
            left.changes, right.cross_repository, left.economics, left.structure
        ),
        "views-economics": lambda: RepositoryViews(
            left.changes, left.cross_repository, right.economics, left.structure
        ),
    }


@pytest.mark.parametrize(
    "component",
    [
        "source",
        "relationships",
        "structure",
        "context",
        "ownership",
        "tasks",
        "dependencies",
        "changes",
        "views-cross",
        "views-economics",
    ],
)
def test_mixed_repository_inputs_reject_before_observation(
    repositories: tuple[CodeMap, CodeMap],
    component: str,
) -> None:
    left, right = repositories
    with pytest.raises(ValueError, match="authority|scope|repository"):
        _mixed_factories(left, right)[component]()


def test_single_input_owners_derive_the_repository_they_observe(
    repositories: tuple[CodeMap, CodeMap],
) -> None:
    _left, right = repositories
    for owner in (
        RepositorySearch(right.native),
        RepositoryVerification(right._imports),
        RepositoryCorrelation(right.bindings),
    ):
        assert owner.reads is right.reads
        assert (
            owner.source.read("owner.py::owner")["content"]
            == "def owner(): return 'right'"
        )


def test_index_rejects_a_store_bound_to_another_workspace(
    repositories: tuple[CodeMap, CodeMap],
) -> None:
    left, right = repositories
    with pytest.raises(ValueError, match="different workspace"):
        RepositoryIndex(
            left.files,
            right.store,
            left.file_store,
            left.artifacts,
            range_provider=left.index.range_provider,
            observation_source=left.index.observation_source,
        )


def test_repository_bindings_expose_one_repository_and_member_revision(
    repositories: tuple[CodeMap, CodeMap],
) -> None:
    left, right = repositories
    declaration = [
        {"binding_id": "owner", "evidence": [{"path": "owner.py", "scope": "member"}]}
    ]
    first = left.bindings.observe(declaration, include_relationships=False)
    second = right.bindings.observe(declaration, include_relationships=False)
    assert (
        assert_object(first["repository"])["repository_identity"]
        != assert_object(second["repository"])["repository_identity"]
    )
    first_member = assert_records(assert_records(first["bindings"])[0]["evidence"])[0]
    second_member = assert_records(assert_records(second["bindings"])[0]["evidence"])[0]
    assert first_member["member_revision"] != second_member["member_revision"]


def test_independent_readers_of_one_shared_store_keep_working(tmp_path: Path) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    member = workspace / "owner.py"
    member.write_text("def before(): return 1\n")
    with (
        CodeMap(
            workspace,
            state_dir=tmp_path / "state",
            artifact_db=tmp_path / "artifacts.sqlite3",
        ) as first,
        CodeMap(
            workspace,
            state_dir=tmp_path / "state",
            artifact_db=tmp_path / "artifacts.sqlite3",
        ) as second,
    ):
        first.index.sync()
        with pytest.raises(ValueError, match="read scope"):
            RepositorySource(first.index, second.reads)
        assert (
            second.source.read("owner.py::before")["content"]
            == "def before(): return 1"
        )
        member.write_text("def after(): return 2\n")
        first.index.sync(["owner.py"])
        assert (
            second.source.read("owner.py::after")["content"] == "def after(): return 2"
        )
        assert first.index.publication_binding() == second.index.publication_binding()
