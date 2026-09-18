from __future__ import annotations

import pytest

from hashmarks.codemap.repository_domains import (
    RepositoryDomain as Domain,
)
from hashmarks.codemap.repository_domains import classify_repository_path


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
        ("src/widget_test.go", (Domain.TEST, Domain.SOURCE)),
        ("app/Widget.test.ts", (Domain.TEST, Domain.SOURCE)),
        ("README.md", (Domain.DOC, Domain.ARCHITECTURE)),
    ],
)
def test_repository_path_domains_preserve_ordered_overlapping_roles(
    path: str, expected: tuple[Domain, ...]
) -> None:
    assert classify_repository_path(path) == expected
