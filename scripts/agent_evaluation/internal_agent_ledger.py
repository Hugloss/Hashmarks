from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path

SCHEMA='hashmarks.internal-agent-ledger.v1'

def _sha(x):
    return 'sha256:'+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _load(p:Path): return json.loads(p.read_text()) if p.exists() else {'schema':SCHEMA,'events':[]}
def _save(p:Path,o): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def _event(state, kind, **kw): state['events'].append({'seq':len(state['events'])+1,'kind':kind,'monotonic_ns':time.monotonic_ns(),**kw})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--state',type=Path,required=True); sp=ap.add_subparsers(dest='cmd',required=True)
    i=sp.add_parser('init'); i.add_argument('--task-id',required=True); i.add_argument('--lane',choices=['native','hashmarks'],required=True); i.add_argument('--repo',type=Path,required=True); i.add_argument('--query',required=True)
    s=sp.add_parser('search'); s.add_argument('--pattern',required=True)
    r=sp.add_parser('read'); r.add_argument('--path',required=True)
    pk=sp.add_parser('packet'); pk.add_argument('--source',type=Path,required=True); pk.add_argument('--budget',type=int,default=512)
    br=sp.add_parser('brief'); br.add_argument('--source',type=Path,required=True); br.add_argument('--budget',type=int,default=512)
    e=sp.add_parser('edit'); e.add_argument('--path',required=True); e.add_argument('--old',required=True); e.add_argument('--new',required=True)
    v=sp.add_parser('verify'); v.add_argument('--path',required=True)
    f=sp.add_parser('finalize'); f.add_argument('--selected-edit',required=True); f.add_argument('--verified',choices=['true','false'],required=True); f.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); st=_load(a.state)
    if a.cmd=='init':
        st={'schema':SCHEMA,'task_id':a.task_id,'lane':a.lane,'repo':str(a.repo.resolve()),'query':a.query,'started_ns':time.monotonic_ns(),'events':[]}; _event(st,'task_received'); _save(a.state,st); return
    repo=Path(st['repo'])
    if a.cmd=='search':
        t=time.perf_counter(); p=subprocess.run(['rg','-n','--glob','!*.pyc',a.pattern,'.'],cwd=repo,text=True,capture_output=True); ms=(time.perf_counter()-t)*1000; out=p.stdout
        _event(st,'search',pattern=a.pattern,wall_ms=ms,result_bytes=len(out.encode()),matches=sum(1 for x in out.splitlines() if x)); _save(a.state,st); print(out,end=''); return
    if a.cmd=='read':
        path=repo/a.path; t=time.perf_counter(); data=path.read_text(); ms=(time.perf_counter()-t)*1000
        _event(st,'read',path=a.path,wall_ms=ms,bytes=len(data.encode())); _save(a.state,st); print(data,end=''); return
    if a.cmd in {'packet','brief'}:
        method='task_decision_packet' if a.cmd=='packet' else 'task_decision_brief'
        code="""import json,sys,time\nfrom pathlib import Path\nfrom hashmarks.codemap import CodeMap\nr=Path(sys.argv[1]); q=sys.argv[2]; b=int(sys.argv[3]); t=time.perf_counter()\nwith CodeMap(r) as c:\n c.sync(); p=getattr(c,sys.argv[4])(q,token_budget=b)\nprint(json.dumps({'wall_ms':(time.perf_counter()-t)*1000,'packet':p},sort_keys=True))\n"""
        env=dict(os.environ); env['PYTHONPATH']=str(a.source.resolve()); t=time.perf_counter(); p=subprocess.run([sys.executable,'-c',code,str(repo),st['query'],str(a.budget),method],env=env,text=True,capture_output=True,check=True); obj=json.loads(p.stdout); packet=obj['packet']; packet_path=a.state.with_suffix('.'+a.cmd+'.json'); packet_path.write_text(json.dumps(packet,indent=2,sort_keys=True)+'\n')
        shown=packet if a.cmd=='brief' else {k:packet.get(k) for k in ('edit','verify','contract','scout','work_context','context_budget')}; bts=len(json.dumps(shown,sort_keys=True).encode()); _event(st,'hashmarks_brief' if a.cmd=='brief' else 'hashmarks_packet',wall_ms=obj['wall_ms'],visible_bytes=bts,packet_identity=(packet.get('identity') or {}).get('decision_generation')); _save(a.state,st); print(json.dumps(shown,indent=2,sort_keys=True)); return
    if a.cmd=='edit':
        path=repo/a.path; text=path.read_text(); changed=a.old in text
        if changed: path.write_text(text.replace(a.old,a.new,1))
        _event(st,'edit',path=a.path,changed=changed); _save(a.state,st); print('changed' if changed else 'unchanged'); return
    if a.cmd=='verify':
        t=time.perf_counter(); p=subprocess.run([sys.executable,'-m','pytest','-q',a.path],cwd=repo,text=True,capture_output=True); ms=(time.perf_counter()-t)*1000
        _event(st,'verification',path=a.path,passed=p.returncode==0,wall_ms=ms,stdout_bytes=len(p.stdout.encode()),stderr_bytes=len(p.stderr.encode())); _save(a.state,st); print(p.stdout,end=''); print(p.stderr,end='',file=sys.stderr); sys.exit(p.returncode)
    if a.cmd=='finalize':
        _event(st,'final_result',selected_edit=a.selected_edit,verified=a.verified=='true'); st['ended_ns']=time.monotonic_ns(); st['sealed']=True
        ev=st['events']; st['metrics']={'tool_calls':sum(x['kind'] in {'search','read','hashmarks_packet','edit','verification'} for x in ev),'search_calls':sum(x['kind']=='search' for x in ev),'read_calls':sum(x['kind']=='read' for x in ev),'repository_read_bytes':sum(x.get('bytes',0)+x.get('result_bytes',0) for x in ev if x['kind'] in {'search','read'}),'hashmarks_visible_bytes':sum(x.get('visible_bytes',0) for x in ev if x['kind'] in {'hashmarks_packet','hashmarks_brief'}),'verification_attempts':sum(x['kind']=='verification' for x in ev),'failed_verifications':sum(x['kind']=='verification' and not x.get('passed') for x in ev),'wall_ms':(st['ended_ns']-st['started_ns'])/1e6}
        frozen=dict(st); frozen.pop('identity',None); st['identity']=_sha(frozen); _save(a.state,st); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(st,indent=2,sort_keys=True)+'\n'); print(st['identity']); return
if __name__=='__main__': main()
