from __future__ import annotations

import pytest

from hashmarks.codemap.repository_domains import (
    RepositoryDomain as Domain,
)
from hashmarks.codemap.repository_domains import classify_repository_path, is_test_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("AGENTS.md", (Domain.OWNERSHIP, Domain.CONTRACT, Domain.DOC)),
        ("Makefile", (Domain.BUILD,)),
        ("templates/plans/task.yaml", (Domain.PLAN, Domain.CONFIG)),
        ("plan.yml", (Domain.PLAN, Domain.CONFIG)),
        ("scripts/check.sh", (Domain.SCRIPT,)),
        (
            "docs/architecture/policy.md",
            (Domain.CONTRACT, Domain.DOC, Domain.ARCHITECTURE),
        ),
        ("tests/test_api.py", (Domain.TEST, Domain.SOURCE)),
        ("src/test_handler.py", (Domain.SOURCE,)),
        ("hashmarks/test_shards.py", (Domain.SOURCE,)),
        ("package/test_runtime.py", (Domain.SOURCE,)),
        ("test_root_contract.py", (Domain.TEST, Domain.SOURCE)),
        ("src/widget_test.go", (Domain.TEST, Domain.SOURCE)),
        ("app/Widget.test.ts", (Domain.TEST, Domain.SOURCE)),
        ("README.md", (Domain.DOC, Domain.ARCHITECTURE)),
    ],
)
def test_repository_path_domains_preserve_ordered_overlapping_roles(
    path: str, expected: tuple[Domain, ...]
) -> None:
    assert classify_repository_path(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_api.py", True),
        ("test_root_contract.py", True),
        ("hashmarks/test_shards.py", False),
        ("package/test_runtime.py", False),
        ("src/widget_test.go", True),
        ("app/Widget.test.ts", True),
    ],
)
def test_is_test_path_matches_repository_domain_semantics(
    path: str, expected: bool
) -> None:
    assert is_test_path(path) is expected
