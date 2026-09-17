from pathlib import Path
from scripts.agent_evaluation.generate_full_edit_corpus import generate

def test_full_edit_corpus_keeps_secret_external_and_is_deterministic(tmp_path:Path):
    a=tmp_path/'a'; p=tmp_path/'public.json'; s=tmp_path/'secret.json'
    m1=generate(a,p,s,cases_per_category=1); p1=p.read_bytes(); s1=s.read_bytes()
    m2=generate(a,p,s,cases_per_category=1)
    assert m1==m2 and p.read_bytes()==p1 and s.read_bytes()==s1
    assert m1['tasks']==6 and m1['secret_outside_worker_roots'] is True
    assert b'expected_edit_path' not in p1

def test_full_edit_cases_start_red(tmp_path:Path):
    import json, runpy, sys
    import pytest
    root=tmp_path/'repos'; p=tmp_path/'p.json'; s=tmp_path/'s.json'; generate(root,p,s,cases_per_category=1)
    secret=json.loads(s.read_text())
    for row in secret['tasks']:
        repo=root/row['id']; verify=repo/row['expected_verify_path']
        sys.path.insert(0, str(repo))
        try:
            namespace = runpy.run_path(str(verify))
            test_functions = [value for name, value in namespace.items() if name.startswith("test_") and callable(value)]
            assert len(test_functions) == 1
            with pytest.raises(AssertionError):
                test_functions[0]()
        finally:
            sys.path.remove(str(repo))
            for name in [name for name in sys.modules if name == "src" or name.startswith("src.")]:
                sys.modules.pop(name, None)
