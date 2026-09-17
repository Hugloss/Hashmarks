from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
_S=Path(__file__).resolve().parent; _R=_S.parent.parent
for x in (str(_R),str(_S)):
 if x not in sys.path: sys.path.insert(0,x)
from hashmarks.codemap import CodeMap
from scripts.experimental_fielded_bm25 import FieldedBM25Index
from .metrics_blind_worker_ab import materialize_challenge,_load_corpus,_sha256_bytes
from .metrics_worker_inspection_ab import _resolve_after_inspection
SCHEMA='hashmarks.bm25-constrained-economics.v1'; FAMILY='hashmarks-v0.10.44-constrained-bm25-a'

def collect(root:Path,limit:int=20)->dict[str,object]:
 reports=[]
 for name,ws,corpus,pub in materialize_challenge(root/'challenge'):
  hidden=_load_corpus(corpus); public=json.load(open(pub))['tasks']; rows=[]
  with CodeMap(ws) as cm:
   cm.sync(); idx=FieldedBM25Index.build(cm)
   for task,secret in zip(public,hidden):
    q=task['query']; expected=set(secret.get('expected_files') or ()); entry=cm.task_entry_points(q,limit=limit); rec=[r for r in entry.get('recommended',[]) if isinstance(r,dict)]; hm=str(rec[0].get('path') or '') if rec else None
    scores={h.path:h.score for h in idx.search(q,limit=100)}
    admitted=[]
    for r in rec:
     path=str(r.get('path') or ''); admitted.append((scores.get(path,0.0),int(r.get('canonical_rank') or 999),path,str(r.get('role') or '')))
    constrained=max(admitted,key=lambda x:(x[0],-x[1],x[2]))[2] if admitted else hm
    ambiguity=entry.get('ambiguity',{}); alternatives=list(ambiguity.get('alternatives',[])) if isinstance(ambiguity,dict) and ambiguity.get('ambiguous') else []
    resolution=_resolve_after_inspection(q,alternatives) if alternatives else {'resolved':False,'target':None}
    role_resolved=str(resolution.get('target') or hm) if resolution.get('resolved') else hm
    rows.append({'id':task['id'],'hashmarks_first':hm,'constrained_bm25_first':constrained,'role_resolved_first':role_resolved,'correct_hashmarks':hm in expected,'correct_constrained_bm25':constrained in expected,'correct_role_resolved':role_resolved in expected,'admitted_candidates':[{'path':p,'role':role,'bm25_score':score,'canonical_rank':rank} for score,rank,p,role in sorted(admitted,key=lambda x:(-x[0],x[1]))]})
  reports.append({'name':name,'public_task_sha256':_sha256_bytes(pub.read_bytes()),'hidden_corpus_sha256':_sha256_bytes(corpus.read_bytes()),'tasks':rows})
 rows=[x for r in reports for x in r['tasks']]; n=len(rows)
 summary={'repositories':len(reports),'tasks':n,'current_hashmarks_correct_first':sum(r['correct_hashmarks'] for r in rows),'constrained_bm25_correct_first':sum(r['correct_constrained_bm25'] for r in rows),'role_resolved_correct_first':sum(r['correct_role_resolved'] for r in rows)}
 summary['bm25_incremental_gain']=summary['constrained_bm25_correct_first']-summary['current_hashmarks_correct_first']; summary['promotion_decision']='reject' if summary['bm25_incremental_gain']<=0 else 'eligible'
 protocol={'family':FAMILY,'constraint':'BM25 may score only task_entry_points admitted paths','role_resolution':'existing public-task ambiguity resolver measured separately','hidden_fields':['expected_files','expected_symbols'],'limit':limit}; ident='sha256:'+hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return {'schema':SCHEMA,'protocol':protocol,'protocol_identity':ident,'summary':summary,'repositories':reports}

def main():
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path); a=p.parse_args(); r=collect(a.root); text=json.dumps(r,indent=2,sort_keys=True)+'\n';
 if a.output: a.output.write_text(text)
 print(text,end='')
if __name__=='__main__': main()
