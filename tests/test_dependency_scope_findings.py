from pathlib import Path
from unittest.mock import patch

from hashmarks.codemap import CodeMap


def _write_dynamic_loader(path: Path, *, root_expression: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\n"
        f"ROOT = {root_expression}\n"
        "spec = spec_from_file_location('pkg.helper', ROOT / 'pkg' / 'helper.py')\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )


def _write_repository_target(root: Path) -> None:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "helper.py").write_text("CACHE = {}\n", encoding="utf-8")


def test_explicit_findings_do_not_read_pruned_dependency_implementation(tmp_path: Path) -> None:
    _write_repository_target(tmp_path)
    dependency = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages" / "demo_dep" / "loader.py"
    _write_dynamic_loader(dependency, root_expression="Path(__file__).resolve().parents[6]")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        with patch(
            "hashmarks.codemap.ownership_analysis.read_python_ast",
            side_effect=AssertionError("pruned dependency source must not be read"),
        ):
            direct = codemap.import_ownership_findings([rel])
        assert direct["summary"]["files_considered"] == 0
        assert direct["findings"] == []

        projected = codemap.repository_findings([rel])
        assert projected["summary"]["findings"] == 0
        assert projected["findings"] == []


def test_explicit_findings_respect_context_policy_index_denial(tmp_path: Path) -> None:
    _write_repository_target(tmp_path)
    private = tmp_path / "private" / "loader.py"
    _write_dynamic_loader(private, root_expression="Path(__file__).resolve().parents[1]")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )
    rel = private.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        result = codemap.import_ownership_findings([rel])
        assert result["summary"]["files_considered"] == 0
        assert result["findings"] == []


def test_findings_scope_pruning_is_segment_aware(tmp_path: Path) -> None:
    _write_repository_target(tmp_path)
    owner = tmp_path / "src" / "node_modules_adapter.py"
    _write_dynamic_loader(owner, root_expression="Path(__file__).resolve().parents[1]")
    rel = owner.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel in codemap.store.paths()
        result = codemap.repository_findings([rel])
        assert result["summary"]["findings"] == 1
        assert result["findings"][0]["path"] == rel
        assert result["findings"][0]["code"] == "python-dynamic-module-identity-bypass"
