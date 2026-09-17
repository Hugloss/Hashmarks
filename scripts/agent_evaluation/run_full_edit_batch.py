from __future__ import annotations
import argparse,json,tempfile
from pathlib import Path
from .full_edit_verify_benchmark import build_combined,run_lane

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--old-source',type=Path,required=True); ap.add_argument('--new-source',type=Path,required=True); ap.add_argument('--corpus-root',type=Path,required=True); ap.add_argument('--public',type=Path,required=True); ap.add_argument('--secret',type=Path,required=True); ap.add_argument('--category',required=True); ap.add_argument('--output',type=Path,required=True)
 a=ap.parse_args(); pub=json.loads(a.public.read_text()); sec=json.loads(a.secret.read_text()); sm={x['id']:x for x in sec['tasks']}; tasks=[t for t in pub['tasks'] if sm[t['id']]['category']==a.category]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td); base=td/'base'; build_combined(a.corpus_root,pub,base)
  old=run_lane(a.old_source,base,tasks,sm,td/'old'); new=run_lane(a.new_source,base,tasks,sm,td/'new')
 out={'schema':'hashmarks.full-edit-verify-category.v1','category':a.category,'old':old,'new':new}; a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps({"category":a.category,"old":{k:v for k,v in old.items() if k!='rows'},"new":{k:v for k,v in new.items() if k!='rows'}},indent=2))
if __name__=='__main__':main()
