from __future__ import annotations

import argparse, hashlib, json, shutil
from pathlib import Path

CATEGORIES=("vocabulary-mismatch","duplicate-symbol-decoy","dead-code-decoy","cross-layer-ownership","configuration-ownership","non-obvious-verification")
SCHEMA="hashmarks.full-edit-agent-corpus.v1"

def _w(p:Path,t:str): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(t,encoding='utf-8')
def _digest(x): return 'sha256:'+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def generate(root:Path, public_path:Path, secret_path:Path, *, cases_per_category:int=10):
    root=root.resolve(); public_path=public_path.resolve(); secret_path=secret_path.resolve()
    for p in (public_path, secret_path):
        try:p.relative_to(root)
        except ValueError:pass
        else: raise ValueError('PUBLIC and SECRET must live outside worker roots')
    if root.exists(): shutil.rmtree(root)
    root.mkdir(parents=True)
    public=[]; secret=[]; idx=0
    for cat in CATEGORIES:
      for variant in range(cases_per_category):
        tid=f'edit-{idx:03d}'; ns=f'case_{idx:03d}'; beh=f'flare{idx:03d}'
        repo=root/tid; owner=f'src/{ns}/engine.py'; route=f'src/{ns}/route.py'; legacy=f'src/{ns}/legacy.py'; config=f'src/{ns}/policy.toml'; verify=f'tests/{ns}/test_behavior.py'
        _w(repo/'pyproject.toml',"[tool.pytest.ini_options]\ntestpaths=['tests']\n")
        _w(repo/'src/__init__.py',''); _w(repo/f'src/{ns}/__init__.py','')
        engine=f"def apply_{ns}(value: str) -> str:\n    return value + '-old'\n"
        route_text=f"from .engine import apply_{ns}\n\ndef handle_{beh}(value: str) -> str:\n    return apply_{ns}(value)\n"
        legacy_text=f"def handle_{beh}(value: str) -> str:\n    return value + '-old'\n"
        query=f"Fix the {beh} accepted response so the active behavior returns the new contract value '-new'"
        expected_edit=owner
        if cat=='duplicate-symbol-decoy': legacy_text+=f"\ndef apply_{ns}(value: str) -> str:\n    return value + '-old'\n"
        elif cat=='dead-code-decoy': legacy_text=f"# exact issue text: {query}\n"+legacy_text+"\nENABLED=False\n"
        elif cat=='cross-layer-ownership':
            _w(repo/f'frontend/{ns}/client.ts',f"export const {beh}=(v:string)=>fetch('/api/{beh}?v='+v);\n")
            query=f"The {beh} frontend request still returns '-old'; fix the active behavior owner so it returns '-new'"
        elif cat=='configuration-ownership':
            _w(repo/config,"mode = 'old'\n")
            engine=("from pathlib import Path\n\n"+f"def apply_{ns}(value: str) -> str:\n    mode='old' if \"mode = 'old'\" in Path(__file__).with_name('policy.toml').read_text() else 'new'\n    return value + '-' + mode\n")
            expected_edit=config
            query=f"Change the {beh} active-path policy from old to new so the accepted response ends '-new'"
        elif cat=='non-obvious-verification':
            verify=f'checks/{ns}/test_contract.py'
            query=f"Repair {beh} so its contract outside the default test tree accepts '-new'"
        elif cat=='vocabulary-mismatch':
            query=f"Accepted responses for request family {beh} must now use contract value '-new' instead of '-old'"
        test=f"from src.{ns}.route import handle_{beh}\n\ndef test_{beh}_contract():\n    assert handle_{beh}('x') == 'x-new'\n"
        _w(repo/owner,engine); _w(repo/route,route_text); _w(repo/legacy,legacy_text); _w(repo/verify,test)
        public.append({'id':tid,'query':query,'repo':tid})
        secret.append({'id':tid,'category':cat,'expected_edit_path':expected_edit,'expected_verify_path':verify,'expected_old':'old','expected_new':'new'})
        idx+=1
    pub={'schema':SCHEMA,'tasks':public}; sec={'schema':SCHEMA,'tasks':secret}
    public_path.parent.mkdir(parents=True,exist_ok=True); secret_path.parent.mkdir(parents=True,exist_ok=True)
    public_path.write_text(json.dumps(pub,indent=2,sort_keys=True)+'\n'); secret_path.write_text(json.dumps(sec,indent=2,sort_keys=True)+'\n')
    return {'schema':'hashmarks.full-edit-agent-corpus-manifest.v1','tasks':len(public),'categories':list(CATEGORIES),'public_identity':_digest(pub),'secret_identity':_digest(sec),'secret_outside_worker_roots':True}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--public',type=Path,required=True); ap.add_argument('--secret',type=Path,required=True); ap.add_argument('--cases-per-category',type=int,default=10); ap.add_argument('--manifest',type=Path)
    a=ap.parse_args(); m=generate(a.root,a.public,a.secret,cases_per_category=a.cases_per_category)
    if a.manifest: a.manifest.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print(json.dumps(m,indent=2,sort_keys=True))
if __name__=='__main__':main()
