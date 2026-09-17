from __future__ import annotations
from hashmarks.codemap import CodeMap
from hashmarks.cli import main

def test_cache_ownership_maps_module_cache_and_unproven_invalidation(tmp_path):
    (tmp_path/"cache_owner.py").write_text("CACHE = {}\n\ndef get(k):\n    return CACHE.get(k)\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result=codemap.cache_ownership_findings()
    assert result["schema"]=="hashmarks.cache-ownership.v1"
    owner=next(x for x in result["owners"] if x["owner"]=="CACHE")
    assert owner["scope"]=="module"
    assert owner["mutable"] is True
    assert owner["invalidation"]=="not-proven"

def test_cache_ownership_maps_lru_cache_as_decorator_managed(tmp_path):
    (tmp_path/"memo.py").write_text(
        "from functools import lru_cache\n@lru_cache(maxsize=8)\ndef value(x):\n    return x\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); result=codemap.cache_ownership_findings()
    owner=next(x for x in result["owners"] if x["owner"]=="value")
    assert owner["kind"]=="decorator:lru_cache"
    assert owner["invalidation"]=="decorator-managed"
    assert owner["confidence"]=="high"

def test_cache_ownership_composes_with_import_identity_risk(tmp_path):
    (tmp_path/"pkg").mkdir()
    (tmp_path/"pkg"/"__init__.py").write_text("",encoding="utf-8")
    (tmp_path/"pkg"/"helper.py").write_text("CACHE = {}\n",encoding="utf-8")
    (tmp_path/"loader.py").write_text(
        "from importlib.util import spec_from_file_location,module_from_spec\n"
        "from pathlib import Path\nROOT=Path(__file__).resolve().parent\n"
        "TARGET=ROOT/'pkg'/'helper.py'\n"
        "spec=spec_from_file_location('copy',str(TARGET))\n"
        "module=module_from_spec(spec)\nspec.loader.exec_module(module)\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); result=codemap.cache_ownership_findings()
    owner=next(x for x in result["owners"] if x["path"]=="pkg/helper.py" and x["owner"]=="CACHE")
    assert owner["import_identity_risk"] is True
    assert "duplicate module identity" in owner["reason"]

def test_cache_ownership_does_not_invent_ordinary_module_state(tmp_path):
    (tmp_path/"plain.py").write_text("VALUES = {}\nCOUNT = 0\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); result=codemap.cache_ownership_findings()
    assert result["owners"]==[]

def test_cli_cache_ownership(tmp_path,capsys):
    (tmp_path/"state.py").write_text("CACHE = {}\n",encoding="utf-8")
    assert main(["map","sync","--workspace",str(tmp_path)])==0; capsys.readouterr()
    assert main(["map","cache-ownership","--workspace",str(tmp_path)])==0
    assert '"schema": "hashmarks.cache-ownership.v1"' in capsys.readouterr().out
