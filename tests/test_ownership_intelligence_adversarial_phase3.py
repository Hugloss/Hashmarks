from __future__ import annotations

from hashmarks.codemap import CodeMap


def _sync(root):
    c = CodeMap(root)
    c.sync()
    return c


def test_import_sys_modules_alias_registration_is_recognized(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "state.py").write_text("CACHE={}\n")
    (tmp_path / "loader.py").write_text(
        "import sys\n"
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'state.py'\n"
        "spec=spec_from_file_location('pkg.state', str(TARGET))\n"
        "module=module_from_spec(spec)\n"
        "modules=sys.modules\n"
        "modules['pkg.state']=module\n"
        "spec.loader.exec_module(module)\n"
    )
    with _sync(tmp_path) as c:
        f = c.import_ownership_findings()["findings"][0]
    assert f["explicit_sys_modules_registration"] is True
    assert f["code"] == "python-custom-module-loader"


def test_cache_transitive_simple_alias_invalidation_is_proven(tmp_path):
    (tmp_path / "state.py").write_text(
        "CACHE={}\nFIRST=CACHE\nSECOND=FIRST\n\ndef reset():\n SECOND.clear()\n"
    )
    with _sync(tmp_path) as c:
        result = c.cache_ownership_findings(["state.py"])
    owner = next(x for x in result["owners"] if x["owner"] == "CACHE")
    assert owner["invalidation"] == "explicit-local-alias"


def test_authority_graph_does_not_attach_reader_to_same_named_cache_in_other_module(
    tmp_path,
):
    (tmp_path / "a.py").write_text("CACHE={}\n")
    (tmp_path / "b.py").write_text("CACHE={}\n")
    (tmp_path / "reader.py").write_text("from a import CACHE\nVALUE=CACHE.get('x')\n")
    with _sync(tmp_path) as c:
        graph = c.repository_ownership_graph()
    edges = [
        e
        for e in graph["edges"]
        if e["relation"] == "references-cache-owner" and e["source"] == "file:reader.py"
    ]
    targets = {e["target"] for e in edges}
    assert "cache:a.py:CACHE" in targets
    assert "cache:b.py:CACHE" not in targets


def test_rmw_mutually_exclusive_match_cases_are_not_joined(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store, value):\n"
        " match value:\n"
        "  case 1:\n   x=store.get('x')\n"
        "  case 2:\n   store.set('x',1)\n"
    )
    with _sync(tmp_path) as c:
        result = c.concurrency_risk_findings(["x.py"])
    assert result["findings"] == []


def test_rmw_calls_inside_uninvoked_lambda_are_not_nominated(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store):\n"
        " callback=lambda: (store.get('x'), store.set('x',1))\n"
        " return callback\n"
    )
    with _sync(tmp_path) as c:
        result = c.concurrency_risk_findings(["x.py"])
    assert result["findings"] == []


def test_rmw_three_match_cases_remain_mutually_exclusive(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store, value):\n"
        " match value:\n"
        "  case 1:\n   x=store.get('x')\n"
        "  case 2:\n   y=1\n"
        "  case 3:\n   store.set('x',1)\n"
    )
    with _sync(tmp_path) as c:
        result = c.concurrency_risk_findings(["x.py"])
    assert result["findings"] == []


def test_repository_wide_rmw_scan_excludes_test_fixture_mutation_but_explicit_path_can_inspect(
    tmp_path,
):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fixture.py").write_text(
        "def test_mutate(tmp_path):\n"
        " path=tmp_path/'x'\n"
        " value=path.read_text()\n"
        " path.write_text(value+'x')\n"
    )
    with _sync(tmp_path) as c:
        broad = c.concurrency_risk_findings()
        explicit = c.concurrency_risk_findings(["tests/test_fixture.py"])
    assert broad["findings"] == []
    assert len(explicit["findings"]) == 1
