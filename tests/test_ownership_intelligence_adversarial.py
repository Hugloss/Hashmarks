from __future__ import annotations
from hashmarks.codemap import CodeMap

def _sync(root):
    c=CodeMap(root); c.sync(); return c

def test_import_alias_same_canonical_identity_is_not_duplicate(tmp_path):
    (tmp_path/"pkg").mkdir(); (tmp_path/"pkg"/"__init__.py").write_text("")
    (tmp_path/"pkg"/"helper.py").write_text("CACHE={}\n")
    (tmp_path/"loader.py").write_text(
      "from importlib.util import spec_from_file_location,module_from_spec\n"
      "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'helper.py'\n"
      "spec=spec_from_file_location('pkg.helper',str(TARGET))\nmodule=module_from_spec(spec)\n"
      "spec.loader.exec_module(module)\n")
    with _sync(tmp_path) as c:
      fs=c.import_ownership_findings()["findings"]
    assert len(fs)==1
    assert fs[0]["module_identity_mismatch"] is False
    assert fs[0]["code"]=="python-dynamic-module-identity-bypass"

def test_import_nonliteral_identity_does_not_invent_mismatch(tmp_path):
    (tmp_path/"pkg").mkdir(); (tmp_path/"pkg"/"__init__.py").write_text("")
    (tmp_path/"pkg"/"helper.py").write_text("CACHE={}\n")
    (tmp_path/"loader.py").write_text(
      "from importlib.util import spec_from_file_location,module_from_spec\n"
      "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'helper.py'\n"
      "name='pkg.'+'helper'\nspec=spec_from_file_location(name,str(TARGET))\n"
      "module=module_from_spec(spec)\nspec.loader.exec_module(module)\n")
    with _sync(tmp_path) as c: f=c.import_ownership_findings()["findings"][0]
    assert f["requested_module"] is None
    assert f["module_identity_mismatch"] is False

def test_cache_local_variable_named_cache_is_not_module_owner(tmp_path):
    (tmp_path/"x.py").write_text("def f():\n cache={}\n return cache\n")
    with _sync(tmp_path) as c:r=c.cache_ownership_findings()
    assert r["owners"]==[]

def test_cache_explicit_clear_is_invalidation_evidence(tmp_path):
    (tmp_path/"x.py").write_text("CACHE={}\ndef reset():\n CACHE.clear()\n")
    with _sync(tmp_path) as c:r=c.cache_ownership_findings()
    o=next(x for x in r["owners"] if x["owner"]=="CACHE")
    assert o["invalidation"]=="explicit-local"

def test_cache_unrelated_clear_does_not_clear_owner(tmp_path):
    (tmp_path/"x.py").write_text("CACHE={}\ndef reset(other):\n other.clear()\n")
    with _sync(tmp_path) as c:r=c.cache_ownership_findings()
    assert next(x for x in r["owners"] if x["owner"]=="CACHE")["invalidation"]=="not-proven"

def test_authority_graph_does_not_claim_runtime_writer(tmp_path):
    (tmp_path/"state.py").write_text("CACHE={}\n")
    (tmp_path/"reader.py").write_text("from state import CACHE\nVALUE=CACHE.get('x')\n")
    with _sync(tmp_path) as c:g=c.repository_ownership_graph()
    assert all(n.get("role")!="writer" for n in g["nodes"])
    assert "no execution/admission/certification authority" in g["boundary"]

def test_rmw_different_owners_is_not_nominated(tmp_path):
    (tmp_path/"x.py").write_text("def f(a,b):\n x=a.get('x')\n b.set('x',x)\n")
    with _sync(tmp_path) as c:r=c.concurrency_risk_findings(["x.py"])
    assert r["findings"]==[]

def test_rmw_write_before_read_is_not_nominated(tmp_path):
    (tmp_path/"x.py").write_text("def f(a):\n a.set('x',1)\n return a.get('x')\n")
    with _sync(tmp_path) as c:r=c.concurrency_risk_findings(["x.py"])
    assert r["findings"]==[]

def test_rmw_nested_unrelated_lock_should_not_guard_sequence(tmp_path):
    (tmp_path/"x.py").write_text(
      "def f(store,other):\n"
      " with other.lock:\n  other.get('x')\n"
      " x=store.get('generation')\n store.set('generation',x+1)\n")
    with _sync(tmp_path) as c:r=c.concurrency_risk_findings(["x.py"])
    f=r["findings"][0]
    assert f["guarded"] is False

def test_rmw_guard_after_sequence_should_not_guard_sequence(tmp_path):
    (tmp_path/"x.py").write_text(
      "def f(store):\n x=store.get('generation')\n store.set('generation',x+1)\n"
      " with store.lock:\n  pass\n")
    with _sync(tmp_path) as c:r=c.concurrency_risk_findings(["x.py"])
    assert r["findings"][0]["guarded"] is False

def test_concurrency_risk_service_and_cli_surface(tmp_path,capsys):
    from hashmarks.cli import main
    (tmp_path/"x.py").write_text("def f(store):\n x=store.get('x')\n store.set('x',x)\n")
    assert main(["map","sync","--workspace",str(tmp_path)])==0; capsys.readouterr()
    assert main(["map","concurrency-risk","--workspace",str(tmp_path),"--path","x.py"])==0
    assert '"schema": "hashmarks.concurrency-risk.v1"' in capsys.readouterr().out
