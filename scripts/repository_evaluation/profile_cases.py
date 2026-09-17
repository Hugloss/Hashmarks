from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hashmarks.codemap import CodeMap
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.common import CASES_SCHEMA, canonical_sha256, load_json, write_json

PROFILE_SCHEMA = "hashmarks.repository-evaluation-profile.v1"
PAIRED_PROFILE_SCHEMA = "hashmarks.repository-evaluation-paired-profile.v1"


def _semantic_fingerprint(action: Mapping[str, object]) -> str:
    payload = json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))]


def _selected_cases(doc: Mapping[str, object], *, shard_count: int, shard_index: int) -> list[Mapping[str, object]]:
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("profile requires non-empty cases")
    return [case for index, case in enumerate(cases) if index % shard_count == shard_index]


def _run_action(codemap: CodeMap, case: Mapping[str, object]) -> tuple[int, str]:
    started = time.perf_counter_ns()
    with codemap.decision_session():
        action = codemap.task_action_map(str(case.get("task") or ""), limit=int(case.get("limit") or 20), per_role=int(case.get("per_role") or 3))
    return time.perf_counter_ns() - started, _semantic_fingerprint(action)


def profile_cases(*, workspace: Path, cases_path: Path, warmups: int = 2, samples: int = 9,
                  shard_count: int = 1, shard_index: int = 0) -> dict[str, Any]:
    if warmups < 0 or samples < 3 or shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid profile protocol")
    doc = load_json(cases_path, schema=CASES_SCHEMA)
    selected = _selected_cases(doc, shard_count=shard_count, shard_index=shard_index)
    workspace = workspace.resolve(); rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="hashmarks-profile-") as state_root:
        state = Path(state_root)
        with CodeMap(workspace, state_dir=state, artifact_db=state / "artifacts.sqlite3") as codemap:
            codemap.sync(); repo_identity = repository_content_identity(workspace, excluded_paths=(codemap.state_dir,))
            for case in selected:
                for _ in range(warmups): _run_action(codemap, case)
                samples_ns=[]; fingerprints=[]
                for _ in range(samples):
                    elapsed, fingerprint = _run_action(codemap, case); samples_ns.append(elapsed); fingerprints.append(fingerprint)
                median=int(statistics.median(samples_ns)); deviations=[abs(value-median) for value in samples_ns]
                rows.append({"id":str(case.get("id") or ""),"task":str(case.get("task") or ""),"samples_ns":samples_ns,"median_ns":median,"p95_ns":_percentile(samples_ns,.95),"mad_ns":int(statistics.median(deviations)),"semantic_fingerprint":fingerprints[0],"semantic_stable":len(set(fingerprints))==1})
    return {"schema":PROFILE_SCHEMA,"suite":doc.get("suite"),"cases_sha256":"sha256:"+canonical_sha256(doc),"repository_identity":repo_identity,"producer_implementation_identity":native_producer_implementation_identity(),"warmups":warmups,"samples":samples,"shard_count":shard_count,"shard_index":shard_index,"cases":rows,"authority":"performance-measurement-only"}


def paired_profile_cases(*, workspace_a: Path, workspace_b: Path, cases_path: Path, warmups: int = 2, pairs: int = 9,
                         shard_count: int = 1, shard_index: int = 0, max_control_mad_pct: float = 10.0) -> dict[str, Any]:
    if warmups < 0 or pairs < 3 or shard_count < 1 or not 0 <= shard_index < shard_count or max_control_mad_pct < 0:
        raise ValueError("invalid paired profile protocol")
    doc=load_json(cases_path,schema=CASES_SCHEMA); selected=_selected_cases(doc,shard_count=shard_count,shard_index=shard_index)
    workspace_a=workspace_a.resolve(); workspace_b=workspace_b.resolve(); rows=[]
    with tempfile.TemporaryDirectory(prefix="hashmarks-paired-a-") as ar, tempfile.TemporaryDirectory(prefix="hashmarks-paired-b-") as br:
        sa=Path(ar); sb=Path(br)
        with CodeMap(workspace_a,state_dir=sa,artifact_db=sa/"artifacts.sqlite3") as a, CodeMap(workspace_b,state_dir=sb,artifact_db=sb/"artifacts.sqlite3") as b:
            a.sync(); b.sync(); aid=repository_content_identity(workspace_a,excluded_paths=(a.state_dir,)); bid=repository_content_identity(workspace_b,excluded_paths=(b.state_dir,))
            for case in selected:
                for _ in range(warmups): _run_action(a,case); _run_action(b,case)
                deltas=[]; semantic_equal=True; af=[]; bf=[]
                for index in range(pairs):
                    if index % 2 == 0:
                        ae,ax=_run_action(a,case); be,bx=_run_action(b,case)
                    else:
                        be,bx=_run_action(b,case); ae,ax=_run_action(a,case)
                    af.append(ax); bf.append(bx); semantic_equal &= ax == bx
                    deltas.append((ae-be)/ae*100.0 if ae else 0.0)
                median=float(statistics.median(deltas)); mad=float(statistics.median(abs(x-median) for x in deltas))
                stable=semantic_equal and len(set(af))==1 and len(set(bf))==1 and mad <= max_control_mad_pct
                rows.append({"id":str(case.get("id") or ""),"task":str(case.get("task") or ""),"paired_gain_pct":deltas,"paired_median_gain_pct":median,"paired_mad_pct":mad,"semantic_equal":semantic_equal,"semantic_stable":len(set(af))==1 and len(set(bf))==1,"admitted":stable,"admission_reason":"ADMITTED" if stable else "SEMANTIC_CHANGE" if not semantic_equal else "UNSTABLE_NOISE"})
    return {"schema":PAIRED_PROFILE_SCHEMA,"suite":doc.get("suite"),"cases_sha256":"sha256:"+canonical_sha256(doc),"repository_identity_a":aid,"repository_identity_b":bid,"producer_implementation_identity":native_producer_implementation_identity(),"warmups":warmups,"pairs":pairs,"shard_count":shard_count,"shard_index":shard_index,"max_control_mad_pct":max_control_mad_pct,"cases":rows,"authority":"performance-measurement-only"}


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path); p.add_argument("--workspace-a",type=Path); p.add_argument("--workspace-b",type=Path); p.add_argument("--cases",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--warmups",type=int,default=2); p.add_argument("--samples",type=int,default=9); p.add_argument("--pairs",type=int); p.add_argument("--max-control-mad-pct",type=float,default=10.0); p.add_argument("--shard-count",type=int,default=1); p.add_argument("--shard-index",type=int,default=0); a=p.parse_args()
    if a.workspace_a or a.workspace_b or a.pairs is not None:
        if not a.workspace_a or not a.workspace_b: p.error("paired profiling requires --workspace-a and --workspace-b")
        result=paired_profile_cases(workspace_a=a.workspace_a,workspace_b=a.workspace_b,cases_path=a.cases,warmups=a.warmups,pairs=a.pairs or a.samples,shard_count=a.shard_count,shard_index=a.shard_index,max_control_mad_pct=a.max_control_mad_pct)
    else:
        if not a.workspace: p.error("profile requires --workspace")
        result=profile_cases(workspace=a.workspace,cases_path=a.cases,warmups=a.warmups,samples=a.samples,shard_count=a.shard_count,shard_index=a.shard_index)
    write_json(a.output,result); return 0

if __name__ == "__main__": raise SystemExit(main())
