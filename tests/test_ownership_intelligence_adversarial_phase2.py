from __future__ import annotations
from hashmarks.codemap import CodeMap

def _sync(root):
    c=CodeMap(root); c.sync(); return c

def test_import_loader_aliases_are_not_invisible(tmp_path):
    (tmp_path/"pkg").mkdir(); (tmp_path/"pkg"/"__init__.py").write_text("")
    (tmp_path/"pkg"/"state.py").write_text("CACHE={}\n")
    (tmp_path/"loader.py").write_text(
        "from importlib.util import spec_from_file_location as make_spec, module_from_spec as make_module\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'state.py'\n"
        "spec=make_spec('shadow.state', str(TARGET))\n"
        "module=make_module(spec)\n"
        "spec.loader.exec_module(module)\n"
    )
    with _sync(tmp_path) as c: result=c.import_ownership_findings()
    assert len(result["findings"])==1
    assert result["findings"][0]["target_module"]=="pkg.state"
    assert result["findings"][0]["requested_module"]=="shadow.state"
    assert result["findings"][0]["code"]=="python-duplicate-module-identity"

def test_cache_invalidation_through_simple_module_alias_is_proven(tmp_path):
    (tmp_path/"state.py").write_text(
        "CACHE={}\nALIAS=CACHE\n\ndef reset():\n ALIAS.clear()\n"
    )
    with _sync(tmp_path) as c: result=c.cache_ownership_findings(["state.py"])
    owner=next(x for x in result["owners"] if x["owner"]=="CACHE")
    assert owner["invalidation"]=="explicit-local-alias"

def test_cache_alias_to_unrelated_owner_does_not_prove_invalidation(tmp_path):
    (tmp_path/"state.py").write_text(
        "CACHE={}\nOTHER={}\nALIAS=OTHER\n\ndef reset():\n ALIAS.clear()\n"
    )
    with _sync(tmp_path) as c: result=c.cache_ownership_findings(["state.py"])
    owner=next(x for x in result["owners"] if x["owner"]=="CACHE")
    assert owner["invalidation"]=="not-proven"

def test_rmw_mutually_exclusive_if_else_is_not_nominated(tmp_path):
    (tmp_path/"x.py").write_text(
        "def f(store, flag):\n"
        " if flag:\n  value=store.get('x')\n"
        " else:\n  store.set('x',1)\n"
    )
    with _sync(tmp_path) as c: result=c.concurrency_risk_findings(["x.py"])
    assert result["findings"]==[]

def test_rmw_nested_function_calls_are_not_attributed_to_outer_function(tmp_path):
    (tmp_path/"x.py").write_text(
        "def outer(store):\n"
        " def inner():\n"
        "  x=store.get('x')\n"
        "  store.set('x',x)\n"
        " return inner\n"
    )
    with _sync(tmp_path) as c: result=c.concurrency_risk_findings(["x.py"])
    assert len(result["findings"])==1
    assert result["findings"][0]["function"]=="inner"

def test_verification_decoy_name_does_not_displace_real_importing_test(tmp_path):
    (tmp_path/"pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    (tmp_path/"src").mkdir(); (tmp_path/"tests").mkdir()
    (tmp_path/"src"/"thing.py").write_text("def calculate_total(x):\n return x+1\n")
    (tmp_path/"tests"/"test_thing.py").write_text(
        "from src.thing import calculate_total\n"
        "def test_calculate_total():\n assert calculate_total(1)==2\n"
    )
    (tmp_path/"tests"/"test_calculate_total_docs.py").write_text(
        "def test_docs_example():\n"
        " text='calculate_total behavior documentation only'\n"
        " assert text\n"
    )
    with _sync(tmp_path) as c:
        graph=c.verification_ownership_graph("change calculate_total behavior",limit=10,candidate_limit=8)
    assert graph["verification_owners"]
    assert graph["verification_owners"][0]["path"]=="tests/test_thing.py"
