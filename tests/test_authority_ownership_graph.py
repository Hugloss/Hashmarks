from hashmarks.codemap import CodeMap
from hashmarks.cli import main

def _repo(root):
    (root/"pkg").mkdir()
    (root/"pkg"/"__init__.py").write_text("",encoding="utf-8")
    (root/"pkg"/"state.py").write_text("CACHE = {}\n",encoding="utf-8")
    (root/"consumer.py").write_text("from pkg.state import CACHE\n\ndef get(k):\n return CACHE.get(k)\n",encoding="utf-8")
    (root/"loader.py").write_text(
      "from importlib.util import spec_from_file_location,module_from_spec\n"
      "from pathlib import Path\nROOT=Path(__file__).resolve().parent\nTARGET=ROOT/'pkg'/'state.py'\n"
      "spec=spec_from_file_location('state_copy',str(TARGET))\nmodule=module_from_spec(spec)\n"
      "spec.loader.exec_module(module)\n",encoding="utf-8")

def test_authority_graph_composes_loader_cache_and_reader(tmp_path):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.repository_ownership_graph()
    assert graph["schema"]=="hashmarks.authority-ownership-graph.v3"
    relations={e["relation"] for e in graph["edges"]}
    assert {"loads-module","owns-cache","references-cache-owner"} <= relations
    cache=next(n for n in graph["nodes"] if n["kind"]=="cache")
    assert cache["owner"]=="CACHE"
    assert cache["id"] in graph["ambiguities"]
    load=next(e for e in graph["edges"] if e["relation"]=="loads-module")
    assert load["risk"]=="python-duplicate-module-identity"
    assert graph["boundary"].startswith("repository-evidence-only")

def test_authority_graph_cli(tmp_path,capsys):
    _repo(tmp_path)
    assert main(["map","sync","--workspace",str(tmp_path)])==0;capsys.readouterr()
    assert main(["map","authority-ownership","--workspace",str(tmp_path)])==0
    out=capsys.readouterr().out
    assert '"schema": "hashmarks.authority-ownership-graph.v3"' in out


def test_authority_graph_v2_composes_exact_imported_invalidator(tmp_path):
    (tmp_path/"state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path/"maintenance.py").write_text(
        "from state import CACHE as SHARED\n\ndef reset():\n    SHARED.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.repository_ownership_graph()
    assert graph["schema"]=="hashmarks.authority-ownership-graph.v3"
    edge=next(e for e in graph["edges"] if e["relation"]=="invalidates-cache")
    assert edge["source"]=="invalidator:maintenance.py:reset"
    assert edge["target"]=="cache:state.py:CACHE"
    assert edge["confidence"]=="qualified-symbol-import"
    assert "cache:state.py:CACHE" not in graph["ambiguities"]
    assert graph["summary"]["resolved_invalidation_owners"]==1
    assert graph["summary"]["unresolved_invalidation_owners"]==0


def test_authority_graph_v2_keeps_unqualified_same_name_invalidator_ambiguous(tmp_path):
    (tmp_path/"a.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path/"b.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path/"maintenance.py").write_text(
        "def reset(CACHE):\n    CACHE.clear()\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.repository_ownership_graph()
    assert not any(e["relation"]=="invalidates-cache" for e in graph["edges"])
    assert set(graph["ambiguities"])=={"cache:a.py:CACHE","cache:b.py:CACHE"}
    assert graph["summary"]["resolved_invalidation_owners"]==0
    assert graph["summary"]["unresolved_invalidation_owners"]==2


def test_authority_graph_v3_composes_unguarded_concurrency_risk_as_nomination(tmp_path):
    (tmp_path/"store.py").write_text(
        "def bump(store):\n current=store.get('generation')\n store.set('generation',current+1)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.repository_ownership_graph(["store.py"])
    assert graph["schema"]=="hashmarks.authority-ownership-graph.v3"
    risk=next(n for n in graph["nodes"] if n["kind"]=="concurrency-risk")
    assert risk["path"]=="store.py" and risk["function"]=="bump"
    assert risk["guarded"] is False
    edge=next(e for e in graph["edges"] if e["relation"]=="contains-concurrency-risk")
    assert edge["source"]=="file:store.py"
    assert edge["target"]==risk["id"]
    assert edge["risk"]=="python-read-modify-write-without-visible-guard"
    assert graph["summary"]["concurrency_risks"]==1
    assert graph["summary"]["unguarded_concurrency_risks"]==1
    assert graph["boundary"].startswith("repository-evidence-only")


def test_authority_graph_v3_keeps_visible_guard_as_non_runtime_proof(tmp_path):
    (tmp_path/"store.py").write_text(
        "def bump(store):\n with store.transaction():\n  current=store.get('generation')\n  store.set('generation',current+1)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.repository_ownership_graph(["store.py"])
    risk=next(n for n in graph["nodes"] if n["kind"]=="concurrency-risk")
    assert risk["guarded"] is True
    assert risk["code"]=="python-read-modify-write-visible-guard"
    assert graph["summary"]["concurrency_risks"]==1
    assert graph["summary"]["unguarded_concurrency_risks"]==0


def test_repository_ownership_graph_materializes_repository_rows_once(tmp_path, monkeypatch):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.store.all_file_rows
        calls = 0

        def counted_all_file_rows():
            nonlocal calls
            calls += 1
            return original()

        monkeypatch.setattr(codemap.store, "all_file_rows", counted_all_file_rows)
        graph = codemap.repository_ownership_graph()

    assert graph["schema"] == "hashmarks.authority-ownership-graph.v3"
    assert calls == 1


def test_scoped_repository_ownership_graph_reuses_rows_without_collapsing_evidence_scope(
    tmp_path, monkeypatch
):
    _repo(tmp_path)
    (tmp_path / "maintenance.py").write_text(
        "from pkg.state import CACHE\n\ndef reset():\n    CACHE.clear()\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.store.all_file_rows
        calls = 0

        def counted_all_file_rows():
            nonlocal calls
            calls += 1
            return original()

        monkeypatch.setattr(codemap.store, "all_file_rows", counted_all_file_rows)
        graph = codemap.repository_ownership_graph(["maintenance.py"])

    assert calls == 1
    assert not any(item["relation"] == "owns-cache" for item in graph["edges"])
    assert not any(item["relation"] == "invalidates-cache" for item in graph["edges"])
