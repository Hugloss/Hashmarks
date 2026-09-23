from __future__ import annotations

from hashmarks.codemap import CodeMap


def _sync(root):
    c = CodeMap(root)
    c.sync()
    return c


def test_import_alias_same_canonical_identity_is_not_duplicate(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "helper.py").write_text("CACHE={}\n")
    (tmp_path / "loader.py").write_text(
        "from importlib.util import spec_from_file_location,module_from_spec\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'helper.py'\n"
        "spec=spec_from_file_location('pkg.helper',str(TARGET))\nmodule=module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
    )
    with _sync(tmp_path) as c:
        fs = c.import_ownership_findings()["findings"]
    assert len(fs) == 1
    assert fs[0]["module_identity_mismatch"] is False
    assert fs[0]["code"] == "python-dynamic-module-identity-bypass"


def test_import_nonliteral_identity_does_not_invent_mismatch(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "helper.py").write_text("CACHE={}\n")
    (tmp_path / "loader.py").write_text(
        "from importlib.util import spec_from_file_location,module_from_spec\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'helper.py'\n"
        "name='pkg.'+'helper'\nspec=spec_from_file_location(name,str(TARGET))\n"
        "module=module_from_spec(spec)\nspec.loader.exec_module(module)\n"
    )
    with _sync(tmp_path) as c:
        f = c.import_ownership_findings()["findings"][0]
    assert f["requested_module"] is None
    assert f["module_identity_mismatch"] is False


def test_cache_local_variable_named_cache_is_not_module_owner(tmp_path):
    (tmp_path / "x.py").write_text("def f():\n cache={}\n return cache\n")
    with _sync(tmp_path) as c:
        r = c.cache_ownership_findings()
    assert r["owners"] == []


def test_cache_explicit_clear_is_invalidation_evidence(tmp_path):
    (tmp_path / "x.py").write_text("CACHE={}\ndef reset():\n CACHE.clear()\n")
    with _sync(tmp_path) as c:
        r = c.cache_ownership_findings()
    o = next(x for x in r["owners"] if x["owner"] == "CACHE")
    assert o["invalidation"] == "explicit-local"


def test_cache_unrelated_clear_does_not_clear_owner(tmp_path):
    (tmp_path / "x.py").write_text("CACHE={}\ndef reset(other):\n other.clear()\n")
    with _sync(tmp_path) as c:
        r = c.cache_ownership_findings()
    assert (
        next(x for x in r["owners"] if x["owner"] == "CACHE")["invalidation"]
        == "not-proven"
    )


def test_authority_graph_does_not_claim_runtime_writer(tmp_path):
    (tmp_path / "state.py").write_text("CACHE={}\n")
    (tmp_path / "reader.py").write_text(
        "from state import CACHE\nVALUE=CACHE.get('x')\n"
    )
    with _sync(tmp_path) as c:
        g = c.repository_ownership_graph()
    assert all(n.get("role") != "writer" for n in g["nodes"])
    assert "no execution/admission/certification authority" in g["boundary"]


def test_rmw_different_owners_is_not_nominated(tmp_path):
    (tmp_path / "x.py").write_text("def f(a,b):\n x=a.get('x')\n b.set('x',x)\n")
    with _sync(tmp_path) as c:
        r = c.concurrency_risk_findings(["x.py"])
    assert r["findings"] == []


def test_rmw_write_before_read_is_not_nominated(tmp_path):
    (tmp_path / "x.py").write_text("def f(a):\n a.set('x',1)\n return a.get('x')\n")
    with _sync(tmp_path) as c:
        r = c.concurrency_risk_findings(["x.py"])
    assert r["findings"] == []


def test_rmw_nested_unrelated_lock_should_not_guard_sequence(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store,other):\n"
        " with other.lock:\n  other.get('x')\n"
        " x=store.get('generation')\n store.set('generation',x+1)\n"
    )
    with _sync(tmp_path) as c:
        r = c.concurrency_risk_findings(["x.py"])
    f = r["findings"][0]
    assert f["guarded"] is False


def test_rmw_guard_after_sequence_should_not_guard_sequence(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store):\n x=store.get('generation')\n store.set('generation',x+1)\n"
        " with store.lock:\n  pass\n"
    )
    with _sync(tmp_path) as c:
        r = c.concurrency_risk_findings(["x.py"])
    assert r["findings"][0]["guarded"] is False


def test_concurrency_risk_service_and_cli_surface(tmp_path, capsys):
    from hashmarks.cli import main

    (tmp_path / "x.py").write_text(
        "def f(store):\n x=store.get('x')\n store.set('x',x)\n"
    )
    assert main(["map", "sync", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    assert (
        main(
            ["map", "concurrency-risk", "--workspace", str(tmp_path), "--path", "x.py"]
        )
        == 0
    )
    assert '"schema": "hashmarks.concurrency-risk.v1"' in capsys.readouterr().out


def test_import_loader_aliases_are_not_invisible(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "state.py").write_text("CACHE={}\n")
    (tmp_path / "loader.py").write_text(
        "from importlib.util import spec_from_file_location as make_spec, module_from_spec as make_module\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'state.py'\n"
        "spec=make_spec('shadow.state', str(TARGET))\n"
        "module=make_module(spec)\n"
        "spec.loader.exec_module(module)\n"
    )
    with _sync(tmp_path) as c:
        result = c.import_ownership_findings()
    assert len(result["findings"]) == 1
    assert result["findings"][0]["target_module"] == "pkg.state"
    assert result["findings"][0]["requested_module"] == "shadow.state"
    assert result["findings"][0]["code"] == "python-duplicate-module-identity"


def test_cache_invalidation_through_simple_module_alias_is_proven(tmp_path):
    (tmp_path / "state.py").write_text(
        "CACHE={}\nALIAS=CACHE\n\ndef reset():\n ALIAS.clear()\n"
    )
    with _sync(tmp_path) as c:
        result = c.cache_ownership_findings(["state.py"])
    owner = next(x for x in result["owners"] if x["owner"] == "CACHE")
    assert owner["invalidation"] == "explicit-local-alias"


def test_cache_alias_to_unrelated_owner_does_not_prove_invalidation(tmp_path):
    (tmp_path / "state.py").write_text(
        "CACHE={}\nOTHER={}\nALIAS=OTHER\n\ndef reset():\n ALIAS.clear()\n"
    )
    with _sync(tmp_path) as c:
        result = c.cache_ownership_findings(["state.py"])
    owner = next(x for x in result["owners"] if x["owner"] == "CACHE")
    assert owner["invalidation"] == "not-proven"


def test_rmw_mutually_exclusive_if_else_is_not_nominated(tmp_path):
    (tmp_path / "x.py").write_text(
        "def f(store, flag):\n"
        " if flag:\n  value=store.get('x')\n"
        " else:\n  store.set('x',1)\n"
    )
    with _sync(tmp_path) as c:
        result = c.concurrency_risk_findings(["x.py"])
    assert result["findings"] == []


def test_rmw_nested_function_calls_are_not_attributed_to_outer_function(tmp_path):
    (tmp_path / "x.py").write_text(
        "def outer(store):\n"
        " def inner():\n"
        "  x=store.get('x')\n"
        "  store.set('x',x)\n"
        " return inner\n"
    )
    with _sync(tmp_path) as c:
        result = c.concurrency_risk_findings(["x.py"])
    assert len(result["findings"]) == 1
    assert result["findings"][0]["function"] == "inner"


def test_verification_decoy_name_does_not_displace_real_importing_test(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "thing.py").write_text("def calculate_total(x):\n return x+1\n")
    (tmp_path / "tests" / "test_thing.py").write_text(
        "from src.thing import calculate_total\n"
        "def test_calculate_total():\n assert calculate_total(1)==2\n"
    )
    (tmp_path / "tests" / "test_calculate_total_docs.py").write_text(
        "def test_docs_example():\n"
        " text='calculate_total behavior documentation only'\n"
        " assert text\n"
    )
    with _sync(tmp_path) as c:
        graph = c.verification_ownership_graph(
            "change calculate_total behavior", limit=10, candidate_limit=8
        )
    assert graph["verification_owners"]
    assert graph["verification_owners"][0]["path"] == "tests/test_thing.py"


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
