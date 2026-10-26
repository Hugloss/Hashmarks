"""Go module syntax interpretation is shared by nomination and import resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.go_module_declaration import declared_go_module


@pytest.mark.parametrize(
    ("manifest", "module"),
    [
        (b"module example.local/demo\ngo 1.23\n", "example.local/demo"),
        (b"// module fake.test/no\nmodule example.local/demo\n", "example.local/demo"),
        (b'module "example.local/demo"\n', "example.local/demo"),
        (b"module example.local/demo // authored\n", "example.local/demo"),
        (b"\n// module example.local/demo\n", None),
        (b"go 1.23\n", None),
        (b"module\n", None),
        (b"module example.local/demo extra\n", None),
        (b"module example.local/demo\nmodule other.test/pkg\n", None),
        (b"module example.local/demo\x00\n", None),
        (b"module \xff\n", None),
    ],
)
def test_go_module_declaration_is_unambiguous_source_syntax(
    manifest: bytes, module: str | None
) -> None:
    assert declared_go_module(manifest) == module


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        (b"module example.local/demo\ngo 1.23\n", True),
        (b"// module example.local/demo\n", False),
        (b"go 1.23\n", False),
        (b"module example.local/demo\nmodule other.test/demo\n", False),
        (b"module \xff\n", False),
    ],
)
def test_go_nomination_requires_authored_module_declaration(
    tmp_path: Path, manifest: bytes, expected: bool
) -> None:
    (tmp_path / "go.mod").write_bytes(manifest)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget_test.go").write_text(
        "package tests\nfunc TestWidget() {}\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/widget_test.go")
    assert nomination["available"] is expected
    assert nomination["execution_authority"] == "external"
    if expected:
        assert nomination["confidence"] == "high"
        assert nomination["runner_evidence"] == "go-test"
        assert isinstance(nomination["supporting_source_members"], list)
        member = nomination["supporting_source_members"][1]
        assert isinstance(member, dict)
        assert member["path"] == "go.mod"
    else:
        assert nomination["reason"] == "source-evidence-unqualified"
    assert {"argv", "executable", "working_directory"}.isdisjoint(nomination)


def test_go_resolver_and_nomination_reuse_same_module_interpreter(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget_test.go").write_text("package tests\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/widget.go").write_text("package pkg\n", encoding="utf-8")
    manifest = tmp_path / "go.mod"
    manifest.write_text("module example.local/demo\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert codemap.verification.nomination("tests/widget_test.go")["available"]
        assert codemap._imports._resolve_go_import_paths("example.local/demo/pkg") == [
            "pkg/widget.go"
        ]
        manifest.write_text("// module example.local/demo\n", encoding="utf-8")
        codemap.index.sync()
        assert codemap.verification.nomination("tests/widget_test.go")["reason"] == (
            "source-evidence-unqualified"
        )
        assert codemap._imports._resolve_go_import_paths("example.local/demo/pkg") == []
