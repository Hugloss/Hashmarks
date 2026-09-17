from __future__ import annotations
import argparse, hashlib, json, sys, time
from pathlib import Path

_SCRIPTS=Path(__file__).resolve().parent; _ROOT=_SCRIPTS.parent.parent
for v in (str(_ROOT),str(_SCRIPTS)):
    if v not in sys.path: sys.path.insert(0,v)
from hashmarks.codemap import CodeMap
from scripts.experimental_fielded_bm25 import FieldedBM25Index
from .metrics_blind_worker_ab import _load_corpus, _sha256_bytes, materialize_challenge
from .metrics_agent_economics import _file_cost, _verification_target

SCHEMA='hashmarks.bm25-economics.v1'; FAMILY='hashmarks-v0.10.43-fielded-bm25-a'

def collect(root:Path,limit:int=20)->dict[str,object]:
    reports=[]; build_ms=0.0
    for name,workspace,corpus,public_path in materialize_challenge(root/'challenge'):
        hidden=_load_corpus(corpus); public=json.loads(public_path.read_text())['tasks']
        with CodeMap(workspace) as cm:
            cm.sync(); t=time.perf_counter(); idx=FieldedBM25Index.build(cm); build_ms+=(time.perf_counter()-t)*1000
            rows=[]
            for task,secret in zip(public,hidden):
                q=task['query']; canonical=cm.task_entry_points(q,limit=limit); rec=[r for r in canonical.get('recommended',[]) if isinstance(r,dict)]
                hm_first=str(rec[0].get('path') or '') if rec else None
                hits=idx.search(q,limit=limit); bm_first=hits[0].path if hits else None
                # Cheap additive fusion: preserve canonical first unless BM25 has a
                # strong role-bearing field match that canonical ranked below it.
                bm_top=hits[0] if hits else None
                use_bm=bool(bm_top and set(bm_top.matched_fields).intersection({'symbol','signature','path'}) and bm_first != hm_first)
                fused_first=bm_first if use_bm else hm_first
                verify,vpos=_verification_target(workspace,q,limit=limit,codemap=cm)
                selected=[fused_first or '',verify or '']; read=_file_cost(workspace,selected)
                exp={str(x) for x in secret.get('expected_files') or ()}
                rows.append({'id':task['id'],'query':q,'hashmarks_first':hm_first,'bm25_first':bm_first,'fused_first':fused_first,'bm25_matched_fields':list(bm_top.matched_fields) if bm_top else [],'bm25_override':use_bm,'correct_hashmarks':hm_first in exp,'correct_bm25':bm_first in exp,'correct_fused':fused_first in exp,'verification_target':verify,'evidence_read':read,'verification_candidates_examined':vpos})
        reports.append({'name':name,'public_task_sha256':_sha256_bytes(public_path.read_bytes()),'hidden_corpus_sha256':_sha256_bytes(corpus.read_bytes()),'tasks':rows})
    rows=[x for r in reports for x in r['tasks']]
    n=len(rows); tokens=sum(int(r['evidence_read']['approx_tokens']) for r in rows)
    summary={'repositories':len(reports),'tasks':n,'bm25_build_ms':build_ms,'current_hashmarks_correct_first':sum(r['correct_hashmarks'] for r in rows),'bm25_correct_first':sum(r['correct_bm25'] for r in rows),'candidate_fused_correct_first':sum(r['correct_fused'] for r in rows),'candidate_fused_wrong_first':sum(not r['correct_fused'] for r in rows),'candidate_bm25_overrides':sum(r['bm25_override'] for r in rows),'candidate_fused_evidence_approx_tokens':tokens,'correct_verifications':sum(bool(r['verification_target']) for r in rows)}; summary['promotion_decision']='reject' if summary['candidate_fused_correct_first'] < summary['current_hashmarks_correct_first'] else 'eligible'; summary['canonical_after_experiment_correct_first']=summary['current_hashmarks_correct_first']
    protocol={'family':FAMILY,'fields':FieldedBM25Index.FIELD_WEIGHTS,'fusion':'canonical-first unless BM25 top has symbol/signature/path field evidence and differs','hidden_fields':['expected_files','expected_symbols'],'limit':limit,'repositories':[{'name':r['name'],'public_task_sha256':r['public_task_sha256'],'hidden_corpus_sha256':r['hidden_corpus_sha256']} for r in reports]}
    ident='sha256:'+hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema':SCHEMA,'protocol':protocol,'protocol_identity':ident,'summary':summary,'repositories':reports}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--limit',type=int,default=20); p.add_argument('--output',type=Path); a=p.parse_args(); r=collect(a.root,a.limit); text=json.dumps(r,indent=2,sort_keys=True)+'\n';
    if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(text)
    print(text,end='')
if __name__=='__main__': main()
