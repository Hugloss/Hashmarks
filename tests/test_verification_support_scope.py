"""Shared-support applicability never asserts runtime fixture consumption."""

from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.evidence_verification import RepositoryVerification
from hashmarks.codemap.import_resolution import RepositoryImports
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.providers import TreeSitterRangeProvider


def _verification(index: RepositoryIndex) -> RepositoryVerification:
    return RepositoryVerification(RepositoryImports(_source(index)))


def _write(index: RepositoryIndex, files: dict[str, str]) -> None:
    for name, source in files.items():
        path = index.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    index.sync()


@pytest.mark.parametrize(
    ("path", "source", "kind", "reason"),
    [
        (
            "tests/test_one.py",
            "def test_one(): pass\n",
            "verifier",
            "python-test-declaration",
        ),
        (
            "tests/test_class.py",
            "class TestCase:\n    def test_one(self): pass\n",
            "verifier",
            "python-test-declaration",
        ),
        (
            "tests/factories.py",
            "def make_record(): return {}\n",
            "verification-support",
            "test-domain-support-source",
        ),
        (
            "src/test_client.py",
            "def test_connection(): return 1\n",
            "source",
            "repository-source",
        ),
        (
            "tests/test_broken.py",
            "def test_broken(: pass\n",
            "unknown",
            "python-source-syntax-unqualified",
        ),
        (
            "tests/test_text.py",
            'EXAMPLE = "def test_example(): pass"\n',
            "verification-support",
            "test-domain-support-source",
        ),
        (
            "tests/data.json",
            '{"test_one": true}\n',
            "verification-support",
            "test-domain-repository-member",
        ),
    ],
)
def test_verifier_role_requires_qualified_declaration(
    index: RepositoryIndex, path: str, source: str, kind: str, reason: str
) -> None:
    _write(index, {path: source})
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_path_kind(path)
    assert observed["kind"] == kind
    assert observed["reason"] == reason
    assert observed["source_member_revision"]
    assert observed["collection_authority"] == "external"


def test_conftest_scope_excludes_siblings_and_preserves_dynamic_unknowns(
    index: RepositoryIndex,
) -> None:
    _write(
        index,
        {
            "packages/left/tests/conftest.py": (
                "import pytest\npytest_plugins = ['plugin']\n"
                "@pytest.fixture\ndef value(request):\n"
                "    return request.getfixturevalue('other')\n"
            ),
            "packages/left/tests/test_value.py": "def test_value(value): pass\n",
            "packages/left/tests/nested/test_override.py": "def test_override(): pass\n",
            "packages/left/tests/factories.py": "def make_value(): return 1\n",
            "packages/right/tests/test_value.py": "def test_value(): pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_support_scope(
            "packages/left/tests/conftest.py", limit=100
        )
    assert observed["targets"] == [
        "packages/left/tests/nested/test_override.py",
        "packages/left/tests/test_value.py",
    ]
    assert observed["completeness"] == "unknown"
    assert observed["truncated"] is False
    assert observed["negative_evidence_admissible"] is False
    assert observed["unsupported_features"] == [
        "dynamic-fixture-consumers-not-observed",
        "pytest-plugin-consumers-not-observed",
    ]
    for row in assert_records(observed["relationships"]):
        assert row["classification"] == "related"
        assert row["relation_kind"] == "pytest-conftest-scope"
        assert row["fixture_consumption"] == "unknown"
        assert row["source_member_revision"]
        assert row["target_member_revision"]


@pytest.mark.parametrize(
    ("name", "config", "expected"),
    [
        ("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', True),
        (
            "pyproject.toml",
            '# [tool.pytest.ini_options]\n[project]\nname = "demo"\n',
            False,
        ),
        ("pytest.ini", "", True),
        ("tox.ini", "[pytest]\naddopts = -q\n", True),
        ("setup.cfg", "[tool:pytest]\naddopts = -q\n", True),
        ("setup.cfg", "[metadata]\nname = demo\n", False),
    ],
)
def test_test_configuration_is_qualified_syntax(
    index: RepositoryIndex, name: str, config: str, expected: bool
) -> None:
    path = f"package/{name}"
    _write(
        index,
        {
            path: config,
            "package/tests/test_one.py": "def test_one(): pass\n",
            "tests/test_other.py": "def test_other(): pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_support_scope(path, limit=100)
    assert observed["targets"] == (["package/tests/test_one.py"] if expected else [])
    assert observed["negative_evidence_admissible"] is False
    if expected:
        assert assert_records(observed["relationships"])[0]["relation_kind"] == (
            "pytest-configuration-scope"
        )


def test_support_projection_bound_cannot_become_negative_evidence(
    index: RepositoryIndex,
) -> None:
    _write(
        index,
        {
            "conftest.py": "# global fixture support\n",
            "tests/test_a.py": "def test_a(): pass\n",
            "tests/test_b.py": "def test_b(): pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        bounded = verification._verification_support_scope("conftest.py", limit=1)
        complete_projection = verification._verification_support_scope(
            "conftest.py", limit=100
        )
    assert bounded["targets"] == ["tests/test_a.py"]
    assert bounded["truncated"] is True
    assert bounded["completeness"] == "incomplete"
    assert bounded["negative_evidence_admissible"] is False
    assert complete_projection["completeness"] == "unknown"
    assert complete_projection["projection_completeness"] == "complete"
    assert complete_projection["evidence_identity"] != bounded["evidence_identity"]


def test_malformed_and_missing_support_remain_unknown(index: RepositoryIndex) -> None:
    _write(
        index,
        {
            "conftest.py": "def bad(: pass\n",
            "pyproject.toml": "[tool.pytest.ini_options\n",
            "tests/test_one.py": "def test_one(): pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        for path in ("conftest.py", "pyproject.toml", "missing.py"):
            kind = verification._verification_path_kind(path)
            observed = verification._verification_support_scope(path, limit=100)
            assert kind["kind"] == "unknown"
            assert observed["targets"] == []
            assert observed["completeness"] == "unknown"
            assert observed["negative_evidence_admissible"] is False


def test_support_identity_tracks_source_revision_and_ignores_fixture_name_coincidence(
    index: RepositoryIndex,
) -> None:
    _write(
        index,
        {
            "tests/conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 1\n",
            "tests/test_a.py": "def test_a(value): pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        first = verification._verification_support_scope("tests/conftest.py", limit=10)
    _write(
        index,
        {
            "tests/conftest.py": "import pytest\n@pytest.fixture\ndef other(): return 2\n"
        },
    )
    with verification.reads.session():
        changed = verification._verification_support_scope(
            "tests/conftest.py", limit=10
        )
    assert first["targets"] == changed["targets"]
    assert first["evidence_identity"] != changed["evidence_identity"]
    assert (
        assert_records(changed["relationships"])[0]["fixture_consumption"] == "unknown"
    )


def test_denied_support_does_not_leak_role_or_consumers(index: RepositoryIndex) -> None:
    _write(
        index,
        {
            "tests/conftest.py": "import pytest\n@pytest.fixture\ndef private(): pass\n",
            "tests/test_private.py": "def test_private(private): pass\n",
            ".hashmarks-context.toml": (
                '[[rule]]\npattern = "tests/conftest.py"\nvisibility = "deny"\n'
            ),
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_support_scope(
            "tests/conftest.py", limit=10
        )
    assert observed["targets"] == []
    source = assert_records(observed["supporting_source_members"])[0]
    assert source["state"] == "unsupported"
    assert "member_revision" not in source


@pytest.mark.parametrize(
    ("path", "source", "kind"),
    [
        ("tests/example.test.js", "import test from 'node:test';\n", "verifier"),
        ("tests/example.test.ts", "const expected: string = 'ok';\n", "verifier"),
        (
            "tests/helpers.js",
            "export function buildRecord() { return {}; }\n",
            "verification-support",
        ),
        ("tests/broken.test.js", "import { from 'broken'", "unknown"),
        ("__tests__/example.js", "import test from 'node:test';\n", "verifier"),
    ],
)
def test_native_test_file_roles_preserve_syntax_unknowns(
    index: RepositoryIndex, path: str, source: str, kind: str
) -> None:
    index.range_provider = TreeSitterRangeProvider.auto()
    _write(index, {path: source})
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_path_kind(path)
    assert observed["kind"] == kind


def test_missing_native_grammar_does_not_invent_verifier(
    index: RepositoryIndex,
) -> None:
    _write(index, {"tests/example.test.js": "import test from 'node:test';\n"})
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_path_kind("tests/example.test.js")
    assert observed["kind"] == "unknown"
    assert observed["reason"] == "native-source-syntax-unavailable"


def test_unqualified_descendant_keeps_scope_incomplete(index: RepositoryIndex) -> None:
    _write(
        index,
        {
            "conftest.py": "# support\n",
            "tests/test_broken.py": "def test_broken(: pass\n",
        },
    )
    verification = _verification(index)
    with verification.reads.session():
        observed = verification._verification_support_scope("conftest.py", limit=10)
    assert observed["completeness"] == "incomplete"
    assert observed["unqualified_candidates"] == ["tests/test_broken.py"]
    assert observed["targets"] == []
    assert observed["negative_evidence_admissible"] is False
