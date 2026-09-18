from __future__ import annotations

import pytest

from hashmarks.codemap.index_surfaces import index_surface_for_path


@pytest.mark.parametrize(
    ("path", "surface"),
    [
        ("uv.lock", "lockfile"),
        ("api/openapi.yaml", "openapi"),
        ("tests/generated/test_client.py", "generated"),
        ("ui/component.snap", "snapshot"),
        ("tests/fixtures/user.json", "fixture"),
        ("app/locales/en.json", "translation"),
        ("tests/test_user.py", "test"),
        ("docs/guide.md", "docs"),
        ("pyproject.toml", "config"),
        ("src/user.py", "source"),
        ("assets/logo.png", "other"),
    ],
)
def test_index_surface_classification_preserves_precedence(
    path: str, surface: str
) -> None:
    assert index_surface_for_path(path) == surface
