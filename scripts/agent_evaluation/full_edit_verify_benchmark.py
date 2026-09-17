from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from statistics import median

def _sha_obj(x): return 'sha256:'+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def packet_all(source:Path, repo:Path, tasks:list[dict])->tuple[dict[str,dict],float]:
    task_json=json.dumps(tasks,separators=(',',':'))
    code="""import json,sys,time\nfrom pathlib import Path\nfrom hashmarks.codemap import CodeMap\nr=Path(sys.argv[1]); tasks=json.loads(sys.argv[2]); out={}\nt=time.perf_counter()\nwith CodeMap(r) as c:\n c.sync()\n for row in tasks: out[row['id']]=c.task_decision_packet(row['query'],token_budget=512)\nprint(json.dumps({'wall_ms':(time.perf_counter()-t)*1000,'packets':out},sort_keys=True))\n"""
    env=dict(os.environ); env['PYTHONPATH']=str(source)
    p=subprocess.run([sys.executable,'-c',code,str(repo),task_json],env=env,text=True,capture_output=True,check=True)
    obj=json.loads(p.stdout); return obj['packets'],float(obj['wall_ms'])

def verify(repo:Path, verify_path:str)->tuple[bool,float]:
    start=time.perf_counter(); p=subprocess.run([sys.executable,'-m','pytest','-q',verify_path],cwd=repo,text=True,capture_output=True)
    return p.returncode==0,(time.perf_counter()-start)*1000

def mutate(path:Path)->bool:
    if not path.exists(): return False
    text=path.read_text()
    if "mode = 'old'" in text: new=text.replace("mode = 'old'","mode = 'new'",1)
    elif "'-old'" in text: new=text.replace("'-old'","'-new'",1)
    else: return False
    path.write_text(new); return True

def build_combined(corpus_root:Path, public:dict, target:Path)->None:
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True); (target/'pyproject.toml').write_text("[tool.pytest.ini_options]\ntestpaths=['tests','checks']\n")
    for task in public['tasks']:
        src=corpus_root/task['repo']
        for top in ('src','tests','checks','frontend'):
            d=src/top
            if not d.exists(): continue
            shutil.copytree(d,target/top,dirs_exist_ok=True)

def run_lane(source:Path, base_repo:Path, tasks:list[dict], secret_map:dict, work:Path)->dict:
    packets, packet_batch_ms=packet_all(source,base_repo,tasks)
    shutil.copytree(base_repo,work)
    rows=[]
    for task in tasks:
        tid=task['id']; truth=secret_map[tid]; packet=packets[tid]; selected=(packet.get('edit') or {}).get('path')
        first_edit_correct=selected==truth['expected_edit_path']
        touched=[]; originals={}
        if selected and (work/selected).exists(): originals[selected]=(work/selected).read_bytes()
        edit_start=time.perf_counter(); changed=mutate(work/selected) if selected else False; edit_ms=(time.perf_counter()-edit_start)*1000
        if changed and selected:touched.append(selected)
        passed,v1=verify(work,truth['expected_verify_path']); attempts=1; recovery=0
        if not passed:
            recovery=1
            # Restore the wrong first edit, then authority-side controlled recovery applies the actual owner.
            for p,b in originals.items(): (work/p).write_bytes(b)
            owner=truth['expected_edit_path']; owner_orig=(work/owner).read_bytes(); changed2=mutate(work/owner)
            if changed2:touched.append(owner)
            passed,v2=verify(work,truth['expected_verify_path']); attempts+=1; verify_ms=v1+v2
            (work/owner).write_bytes(owner_orig)
        else:
            verify_ms=v1
            for p,b in originals.items(): (work/p).write_bytes(b)
        rows.append({'id':tid,'category':truth['category'],'selected_edit_path':selected,'first_edit_correct':first_edit_correct,'first_verification_passed':attempts==1 and passed,'verified_solution':passed,'verification_attempts':attempts,'recovery_attempts':recovery,'files_touched':len(set(touched)),'edit_ms':edit_ms,'verify_ms':verify_ms,'time_to_green_ms':edit_ms+verify_ms})
    n=len(rows); verified=sum(r['verified_solution'] for r in rows); first=sum(r['first_edit_correct'] for r in rows)
    return {'tasks':n,'first_edit_correct':first,'first_edit_correct_rate':first/n,'first_verification_passed':sum(r['first_verification_passed'] for r in rows),'verified_solutions':verified,'verified_solution_rate':verified/n,'verification_attempts':sum(r['verification_attempts'] for r in rows),'recovery_attempts':sum(r['recovery_attempts'] for r in rows),'files_touched':sum(r['files_touched'] for r in rows),'median_time_to_green_ms':median(r['time_to_green_ms'] for r in rows),'packet_batch_ms':packet_batch_ms,'packet_ms_per_task':packet_batch_ms/n,'rows':rows}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--old-source',type=Path,required=True); ap.add_argument('--new-source',type=Path,required=True); ap.add_argument('--corpus-root',type=Path,required=True); ap.add_argument('--public',type=Path,required=True); ap.add_argument('--secret',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); pub=json.loads(a.public.read_text()); sec=json.loads(a.secret.read_text()); sm={x['id']:x for x in sec['tasks']}
    with tempfile.TemporaryDirectory() as td:
      td=Path(td); base=td/'combined'; build_combined(a.corpus_root,pub,base)
      old=run_lane(a.old_source,base,pub['tasks'],sm,td/'old'); new=run_lane(a.new_source,base,pub['tasks'],sm,td/'new')
    payload={'schema':'hashmarks.full-edit-verify-comparison.v1','protocol':{'same_public_tasks':True,'single_repository_generation_per_lane':True,'secret_join_after_packet':True,'first_edit_selected_only_from_worker_packet':True,'real_pytest_verification':True,'recovery_executor':'authority-side controlled recovery after failed verification','claim_scope':'causal downstream effect of ownership target; not model-token economics'},'old':old,'new':new,'delta':{'first_edit_correct':new['first_edit_correct']-old['first_edit_correct'],'first_verification_passed':new['first_verification_passed']-old['first_verification_passed'],'verification_attempts':new['verification_attempts']-old['verification_attempts'],'recovery_attempts':new['recovery_attempts']-old['recovery_attempts'],'files_touched':new['files_touched']-old['files_touched'],'median_time_to_green_ms':new['median_time_to_green_ms']-old['median_time_to_green_ms'],'packet_ms_per_task':new['packet_ms_per_task']-old['packet_ms_per_task']}}
    payload['identity']=_sha_obj(payload); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    print('old', {k:v for k,v in old.items() if k!='rows'}); print('new',{k:v for k,v in new.items() if k!='rows'}); print('delta',payload['delta']); print('identity',payload['identity'])
if __name__=='__main__':main()
