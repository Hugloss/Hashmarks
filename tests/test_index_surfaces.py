from __future__ import annotations

import pytest

from hashmarks.codemap.index_surfaces import index_surface_for_path


@pytest.mark.parametrize(
    ("path", "surface"),
    [
        # Special Surfaces (Highest Precedence)
        ("uv.lock", "lockfile"),
        ("any-file.lock", "lockfile"),
        ("api/openapi.yaml", "openapi"),
        ("swagger.json", "openapi"),
        ("tests/generated/test_client.py", "generated"),
        ("src/foo_generated.py", "generated"),
        ("dist/bundle.js", "generated"),
        ("ui/component.snap", "snapshot"),
        ("debug.snap", "snapshot"),
        ("tests/fixtures/user.json", "fixture"),
        ("testdata/input.txt", "fixture"),
        ("app/locales/en.json", "translation"),
        ("i18n/messages.po", "translation"),
        # Precedence checks: Special > Test > Docs > Config > Source
        ("tests/uv.lock", "lockfile"),  # Special beats Test
        ("docs/openapi.yaml", "openapi"),  # Special beats Docs
        ("src/generated/foo.py", "generated"),  # Special beats Source
        # Standard Surfaces
        ("tests/test_user.py", "test"),
        ("src/test_util.py", "source"),
        ("packages/app/src/test_util.py", "source"),
        ("src/tests/test_util.py", "test"),
        ("docs/guide.md", "docs"),
        ("docs/index.rst", "docs"),
        ("README.adoc", "docs"),
        ("pyproject.toml", "config"),
        ("package.json", "config"),
        ("Makefile", "config"),
        ("settings.yaml", "config"),
        ("src/user.py", "source"),
        ("main.go", "source"),
        ("lib.rs", "source"),
        ("app.java", "source"),
        # Fallback
        ("assets/logo.png", "other"),
        ("LICENSE", "other"),
    ],
)
def test_index_surface_classification_preserves_precedence(
    path: str, surface: str
) -> None:
    assert index_surface_for_path(path) == surface
