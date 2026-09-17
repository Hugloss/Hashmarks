from __future__ import annotations

from hashmarks.codemap import CodeMap
from hashmarks.cli import main


def _write_package(repo, *, loader_path="scripts/research.py", register=False):
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "scripts" / "helper.py").write_text(
        "CACHE = {}\n\ndef value():\n    return CACHE\n", encoding="utf-8"
    )
    target = repo / loader_path
    target.parent.mkdir(parents=True, exist_ok=True)
    registration = "sys.modules[spec.name] = module\n" if register else ""
    imports = "import sys\n" if register else ""
    target.write_text(
        imports
        + "from importlib.util import spec_from_file_location, module_from_spec\n"
        + "from pathlib import Path\n"
        + "ROOT = Path(__file__).resolve().parents[1]\n"
        + "spec = spec_from_file_location('scripts.helper', ROOT / 'scripts' / 'helper.py')\n"
        + "module = module_from_spec(spec)\n"
        + registration
        + "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )


def test_import_ownership_reports_repository_owned_dynamic_module_bypass(tmp_path):
    _write_package(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings()

    assert result["schema"] == "hashmarks.import-ownership.v2"
    assert result["summary"]["warnings"] == 1
    assert result["summary"]["advisories"] == 0
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["path"] == "scripts/research.py"
    assert finding["code"] == "python-dynamic-module-identity-bypass"
    assert finding["target_path"] == "scripts/helper.py"
    assert finding["target_module"] == "scripts.helper"
    assert finding["domain"] == "source"
    assert finding["severity"] == "warning"
    assert finding["confidence"] == "high"


def test_import_ownership_does_not_flag_normal_package_import(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "scripts" / "helper.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "scripts" / "research.py").write_text(
        "from scripts import helper\n\ndef get():\n    return helper.CACHE\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings()
    assert result["findings"] == []


def test_import_ownership_downgrades_test_loader_to_advisory(tmp_path):
    _write_package(tmp_path, loader_path="tests/test_loader.py")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings()
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["domain"] == "test"
    assert finding["severity"] == "advisory"
    assert finding["target_module"] == "scripts.helper"


def test_import_ownership_recognizes_explicit_sys_modules_owner(tmp_path):
    _write_package(tmp_path, register=True)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings()
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["code"] == "python-custom-module-loader"
    assert finding["explicit_sys_modules_registration"] is True
    assert finding["severity"] == "advisory"


def test_import_ownership_can_inspect_explicit_path(tmp_path):
    _write_package(tmp_path)
    (tmp_path / "other.py").write_text("value = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings(["scripts/research.py"])
    assert result["summary"]["files_considered"] == 1
    assert result["findings"][0]["path"] == "scripts/research.py"


def test_cli_map_import_ownership_exposes_static_diagnostic(tmp_path, capsys):
    _write_package(tmp_path)
    assert main(["map", "sync", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["map", "import-ownership", "--workspace", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert '"schema": "hashmarks.import-ownership.v2"' in output
    assert '"target_module": "scripts.helper"' in output


def test_import_ownership_resolves_bound_and_wrapped_target_path(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "helper.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "loader.py").write_text(
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parent\n"
        "TARGET = ROOT / 'pkg' / 'helper.py'\n"
        "spec = spec_from_file_location('pkg.helper', str(TARGET))\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.import_ownership_findings()
    assert result["findings"][0]["target_path"] == "pkg/helper.py"
    assert result["findings"][0]["target_module"] == "pkg.helper"


def test_import_ownership_reports_duplicate_module_identity(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "helper.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "loader.py").write_text(
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parent\n"
        "TARGET = ROOT / 'pkg' / 'helper.py'\n"
        "spec = spec_from_file_location('private_helper_copy', str(TARGET))\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        finding = codemap.import_ownership_findings()["findings"][0]
    assert finding["code"] == "python-duplicate-module-identity"
    assert finding["target_module"] == "pkg.helper"
    assert finding["requested_module"] == "private_helper_copy"
    assert finding["module_identity_mismatch"] is True
    assert "pkg.helper" in finding["recommendation"]
