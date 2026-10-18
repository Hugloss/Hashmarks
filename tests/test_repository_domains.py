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
    ("path", "test_role"),
    [
        ("src/service/test_driver.py", False),
        ("lib/server/test_adapter.py", False),
        ("app/test_routes.py", False),
        ("src/service/tests/test_driver.py", True),
        ("tests/test_driver.py", True),
        ("testing/helpers.py", True),
        ("driver_test.py", True),
        ("src/service/driver_test.py", False),
        ("app/Driver.test.ts", True),
    ],
)
def test_test_role_and_verification_path_share_one_classification(
    path: str,
    test_role: bool,
) -> None:
    assert (Domain.TEST in classify_repository_path(path)) is test_role
    assert is_test_path(path) is test_role
