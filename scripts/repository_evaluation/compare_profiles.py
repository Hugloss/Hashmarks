from __future__ import annotations
import argparse, math, statistics, sys
from pathlib import Path
from typing import Any, Mapping
if __package__ in {None, ""}: sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.repository_evaluation.common import load_json, write_json
from scripts.repository_evaluation.profile_cases import PROFILE_SCHEMA

def _p90(values: list[float]) -> float:
    if not values: return 0.0
    ordered=sorted(values); return ordered[min(len(ordered)-1,max(0,math.ceil(.9*len(ordered))-1))]

def compare_profiles(*, baseline: Mapping[str, object], candidate: Mapping[str, object], repeat: Mapping[str, object] | None=None, minimum_gain_pct: float=3.0) -> dict[str, Any]:
    def rows(doc): return {str(row["id"]):row for row in doc.get("cases",[])}
    b,c=rows(baseline),rows(candidate); r=rows(repeat) if repeat else {}
    if set(b)!=set(c): raise ValueError("profile case membership mismatch")
    noise_by_case={}
    for case_id in b:
        if case_id in r:
            base=float(b[case_id]["median_ns"]); noise_by_case[case_id]=abs(base-float(r[case_id]["median_ns"]))/base*100.0 if base else 0.0
        else: noise_by_case[case_id]=0.0
    global_noise=_p90(list(noise_by_case.values()))
    output=[]
    for case_id in sorted(b):
        br,cr=b[case_id],c[case_id]; semantic_equal=br.get("semantic_fingerprint")==cr.get("semantic_fingerprint") and bool(br.get("semantic_stable")) and bool(cr.get("semantic_stable"))
        base=float(br["median_ns"]); cand=float(cr["median_ns"]); raw=(base-cand)/base*100.0; noise=noise_by_case[case_id]; threshold=max(float(minimum_gain_pct),noise)
        decision="SEMANTIC_CHANGE" if not semantic_equal else "WIN" if raw>threshold else "REGRESSION" if raw < -threshold else "NOISE_BAND"
        output.append({"id":case_id,"baseline_median_ns":int(base),"candidate_median_ns":int(cand),"raw_gain_pct":raw,"same_version_noise_pct":noise,"required_gain_pct":threshold,"semantic_equal":semantic_equal,"decision":decision})
    return {"schema":"hashmarks.repository-evaluation-profile-comparison.v1","cases":output,"wins":sum(x["decision"]=="WIN" for x in output),"semantic_changes":sum(x["decision"]=="SEMANTIC_CHANGE" for x in output),"noise_floor_percent":global_noise,"noise_floor_authority":"per-case same-version noise; global p90 is diagnostic only"}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--baseline",type=Path,required=True); p.add_argument("--candidate",type=Path,required=True); p.add_argument("--repeat",type=Path); p.add_argument("--output",type=Path,required=True); p.add_argument("--minimum-gain-pct",type=float,default=3.0); a=p.parse_args(); result=compare_profiles(baseline=load_json(a.baseline,schema=PROFILE_SCHEMA),candidate=load_json(a.candidate,schema=PROFILE_SCHEMA),repeat=load_json(a.repeat,schema=PROFILE_SCHEMA) if a.repeat else None,minimum_gain_pct=a.minimum_gain_pct); write_json(a.output,result); return 0
if __name__=="__main__": raise SystemExit(main())
