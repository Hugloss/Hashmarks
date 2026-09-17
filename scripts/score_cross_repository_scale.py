from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import time
from pathlib import Path
from typing import Iterable

from hashmarks import __version__
from hashmarks.codemap import CodeMap, expand_project_impact
from scripts.agent_evaluation.experimentability import EvidenceEconomics, experiment_environment, experiment_record

SCHEMA_PUBLIC = "hashmarks.cross-repository-scale-public.v1"
SCHEMA_SECRET = "hashmarks.cross-repository-scale-secret.v1"
SCHEMA_RESULT = "hashmarks.cross-repository-scale-qualification.v1"


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _project_id(index: int) -> str:
    return f"npm:@scale/p{index:04d}"


def _write_project(root: Path, index: int) -> str:
    project = root / "projects" / f"p{index:04d}"
    (project / "src").mkdir(parents=True)
    name = f"@scale/p{index:04d}"
    (project / "package.json").write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
    suffix = ("py", "ts", "go")[index % 3]
    filenames = {"py": "owner.py", "ts": "owner.ts", "go": "owner.go"}
    body = {
        "py": f"VALUE = 'p{index:04d}'\n",
        "ts": f"export const value = 'p{index:04d}';\n",
        "go": f"package p{index:04d}\nconst Value = \"p{index:04d}\"\n",
    }
    (project / "src" / filenames[suffix]).write_text(body[suffix], encoding="utf-8")
    return (project / "src" / filenames[suffix]).relative_to(root).as_posix()


def _edges(shape: str, count: int) -> list[tuple[int, int, str]]:
    if count < 2:
        return []
    if shape == "chain":
        return [(i, i - 1, "chain") for i in range(1, count)]
    if shape == "fanout":
        return [(i, 0, "fanout") for i in range(1, count)]
    if shape == "fanin":
        # A wide lower layer converges into one dependent, with the changed root
        # at p0. This exercises repeated reachability without changing semantics.
        rows = [(i, 0, "fanin-leaf") for i in range(1, max(2, count - 1))]
        sink = count - 1
        rows.extend((sink, i, "fanin-sink") for i in range(1, sink))
        return rows
    if shape == "diamond":
        rows: list[tuple[int, int, str]] = []
        # Repeated diamonds: base -> left/right -> join -> next base.
        base = 0
        nxt = 1
        while nxt < count:
            left = nxt; nxt += 1
            if left < count: rows.append((left, base, "diamond-left"))
            if nxt >= count: break
            right = nxt; nxt += 1
            rows.append((right, base, "diamond-right"))
            if nxt >= count: break
            join = nxt; nxt += 1
            rows.append((join, left, "diamond-join"))
            rows.append((join, right, "diamond-join"))
            base = join
        return rows
    raise ValueError(shape)


def _reverse_expected(edges: Iterable[tuple[int, int, str]], roots: set[int], max_depth: int) -> tuple[dict[int, int], list[tuple[int, int, str]]]:
    reverse: dict[int, list[tuple[int, str]]] = {}
    for source, target, kind in edges:
        reverse.setdefault(target, []).append((source, kind))
    seen = set(roots)
    frontier = sorted(roots)
    depths: dict[int, int] = {}
    admitted_edges: list[tuple[int, int, str]] = []
    for depth in range(1, max_depth + 1):
        nxt: list[int] = []
        for current in frontier:
            for source, kind in sorted(reverse.get(current, [])):
                if source in seen:
                    continue
                seen.add(source); depths[source] = depth; nxt.append(source)
                admitted_edges.append((source, current, kind))
        if not nxt: break
        frontier = sorted(nxt)
    return depths, admitted_edges


def _write_scenario(root: Path, *, shape: str, count: int, contracts: int) -> tuple[dict, dict]:
    source_paths = [_write_project(root, i) for i in range(count)]
    edges = _edges(shape, count)
    link_lines = []
    for source, target, kind in edges:
        link_lines.append(f"[[link]]\nsource='{_project_id(source)}'\ntarget='{_project_id(target)}'\nkind='{kind}'\n")
    shared_paths = []
    (root / "contracts").mkdir(exist_ok=True)
    for n in range(contracts):
        shared = f"contracts/contract-{n}.yaml"; shared_paths.append(shared)
        (root / shared).write_text(f"openapi: 3.1.0\ninfo:\n  title: scale-{shape}-{count}-{n}\n", encoding="utf-8")
        # Bind each contract to a deterministic sparse set, including root.
        selected = sorted({0, min(count - 1, n + 1), count - 1})
        ids = ",".join(repr(_project_id(i)) for i in selected)
        link_lines.append(f"[[shared_input]]\npath='{shared}'\nprojects=[{ids}]\nkind='contract'\n")
    (root / ".hashmarks-project-links.toml").write_text("".join(link_lines), encoding="utf-8")

    depth_budget = max(4, count + 2)
    expected_depths, expected_edges = _reverse_expected(edges, {0}, depth_budget)
    task_id = f"{shape}-{count}-source"
    public = {
        "id": task_id, "repo": root.name, "shape": shape, "projects": count,
        "kind": "source", "changed": source_paths[0], "query": f"Update {shape} scale root implementation",
        "max_depth": depth_budget,
    }
    secret = {
        "id": task_id,
        "projects": sorted(_project_id(i) for i in expected_depths),
        "depths": {_project_id(i): depth for i, depth in expected_depths.items()},
        "edges": [[_project_id(s), _project_id(t), k] for s, t, k in expected_edges],
    }
    # Add one shared-input mutation scenario at each size/shape. Expected roots
    # are the explicitly bound projects plus their dependents.
    shared_roots = {0, min(count - 1, 1), count - 1}
    shared_depths, shared_edges = _reverse_expected(edges, shared_roots, depth_budget)
    shared_id = f"{shape}-{count}-shared"
    public_shared = {
        "id": shared_id, "repo": root.name, "shape": shape, "projects": count,
        "kind": "shared-input", "changed": shared_paths[0], "query": f"Update {shape} scale shared contract",
        "max_depth": depth_budget,
    }
    secret_shared = {
        "id": shared_id,
        # roots themselves appear in affected projects for a shared input.
        "projects": sorted({_project_id(i) for i in shared_roots} | {_project_id(i) for i in shared_depths}),
        "depths": {_project_id(i): 1 for i in shared_roots} | {_project_id(i): d + 1 for i, d in shared_depths.items()},
        "edges": [[_project_id(s), _project_id(t), k] for s, t, k in shared_edges],
    }
    return {"tasks": [public, public_shared]}, {"tasks": [secret, secret_shared]}


def generate(base: Path, public_path: Path, secret_path: Path, *, sizes: list[int], shapes: list[str], contracts: int) -> dict:
    if base.exists(): shutil.rmtree(base)
    base.mkdir(parents=True)
    public_rows=[]; secret_rows=[]
    for shape in shapes:
        for count in sizes:
            repo=base/f"{shape}-{count:04d}"; repo.mkdir()
            pub, sec=_write_scenario(repo, shape=shape, count=count, contracts=contracts)
            public_rows.extend(pub["tasks"]); secret_rows.extend(sec["tasks"])
    public={"schema":SCHEMA_PUBLIC,"tasks":public_rows}
    secret={"schema":SCHEMA_SECRET,"tasks":secret_rows}
    public_path.write_text(json.dumps(public,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    secret_path.write_text(json.dumps(secret,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"tasks":len(public_rows),"sizes":sizes,"shapes":shapes,"public_identity":_digest(public),"secret_identity":_digest(secret),"answer_key_inside_worker_repo":False}


def run(base: Path, public_path: Path, secret_path: Path, output: Path, *, provenance_limit: int=6, provenance_encoding: str="verbose") -> dict:
    public=json.loads(public_path.read_text(encoding="utf-8"))["tasks"]
    frozen=[]
    for task in public:
        repo=base/task["repo"]
        with CodeMap(repo, artifact_db=repo/"artifacts.sqlite3") as codemap:
            t0=time.perf_counter_ns(); codemap.sync(); codemap.enrich_projects(("npm-package-graph","declared-project-links")); setup_ns=time.perf_counter_ns()-t0
            changed=repo/task["changed"]
            if task["kind"]=="shared-input": changed.write_text(changed.read_text().replace("openapi: 3.1.0","openapi: 3.1.1"),encoding="utf-8")
            else: changed.write_text(changed.read_text()+"\n# external edit\n",encoding="utf-8")
            meter=EvidenceEconomics(); t1=time.perf_counter_ns()
            packet=codemap.task_change_impact(task["query"],[task["changed"]],max_depth=int(task["max_depth"]),impact_limit_per_surface=6,project_impact_limit=provenance_limit,project_impact_encoding=provenance_encoding)
            elapsed=time.perf_counter_ns()-t1
            economics=meter.finish(evidence=packet,elapsed_ns=elapsed,refresh_ns=None)
            environment=experiment_environment(hashmarks_version=__version__,repository_identity=_digest({"repo":task["repo"]}),codemap_generation=codemap.store.generation(),identity_generation=None,provider_revisions={"declared-project-links":"current"},cache_state="warm")
            record=experiment_record(task_id=task["id"],task_identity=_digest(task),environment=environment,decision_packet=packet,economics=economics)
        frozen.append({"task":task,"packet":packet,"record":record,"setup_ms":setup_ns/1_000_000})

    # SECRET is intentionally opened only after every Hashmarks packet is frozen.
    secret={r["id"]:r for r in json.loads(secret_path.read_text(encoding="utf-8"))["tasks"]}
    rows=[]
    for item in frozen:
        task=item["task"]; packet=item["packet"]; expected=secret[task["id"]]
        projects=set(map(str,packet.get("projects",[])))
        expected_projects=set(map(str,expected["projects"]))
        fragment=packet.get("project_impact") if isinstance(packet.get("project_impact"),dict) else {}
        fragment=expand_project_impact(fragment)
        affected={str(r.get("project")):int(r.get("depth",-1)) for r in fragment.get("affected",[]) if isinstance(r,dict)}
        expected_depths={str(k):int(v) for k,v in expected["depths"].items()}
        provenance_recall=sum(1 for k,v in expected_depths.items() if affected.get(k)==v)/max(1,len(expected_depths))
        project_recall=len(projects & expected_projects)/max(1,len(expected_projects))
        project_precision=len(projects & expected_projects)/max(1,len(projects)) if projects else (1.0 if not expected_projects else 0.0)
        edges=fragment.get("edges",[]) if isinstance(fragment,dict) else []
        producer_complete=all(isinstance(e,dict) and e.get("producer")=="declared-project-links" for e in edges)
        refresh_ok=True
        if task["kind"]=="shared-input":
            refresh=packet.get("project_refresh"); refresh_ok=isinstance(refresh,dict) and refresh.get("producer")=="declared-project-links"
        rows.append({
            "id":task["id"],"shape":task["shape"],"projects_total":task["projects"],"kind":task["kind"],
            "expected_projects":len(expected_projects),"reported_projects":len(projects),"project_recall":project_recall,"project_precision":project_precision,
            "expected_provenance_rows":len(expected_depths),"reported_provenance_rows":len(affected),"provenance_recall":provenance_recall,
            "producer_complete":producer_complete,"refresh_correct":refresh_ok,"packet_bytes":item["record"]["economics"]["evidence_bytes"],
            "impact_ms":item["record"]["economics"]["decision_latency_ms"],"setup_ms":item["setup_ms"],
            "fully_correct":project_recall==1.0 and project_precision==1.0 and provenance_recall==1.0 and producer_complete and refresh_ok,
            "record_identity":item["record"]["record_identity"],
        })
    summary={
        "tasks":len(rows),"fully_correct":sum(int(r["fully_correct"]) for r in rows),
        "project_recall_mean":statistics.fmean(r["project_recall"] for r in rows),
        "provenance_recall_mean":statistics.fmean(r["provenance_recall"] for r in rows),
        "mean_packet_bytes":statistics.fmean(r["packet_bytes"] for r in rows),
        "mean_impact_ms":statistics.fmean(r["impact_ms"] for r in rows),
        "max_impact_ms":max(r["impact_ms"] for r in rows),
        "mean_setup_ms":statistics.fmean(r["setup_ms"] for r in rows),
        "provenance_limit":provenance_limit,"provenance_encoding":provenance_encoding,
    }
    payload={"schema":SCHEMA_RESULT,"protocol":{"public_only_until_packets_frozen":True,"secret_join_after_packet_freeze":True,"execution_owner":"external","product_source_changed_during_measurement":False},"summary":summary,"rows":rows}
    output.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return payload


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("base",type=Path); ap.add_argument("public",type=Path); ap.add_argument("secret",type=Path); ap.add_argument("output",type=Path)
    ap.add_argument("--sizes",default="10,50,100,500"); ap.add_argument("--provenance-encoding",choices=("verbose","compact"),default="verbose"); ap.add_argument("--shapes",default="chain,fanout,fanin,diamond"); ap.add_argument("--contracts",type=int,default=2); ap.add_argument("--provenance-limit",type=int,default=6); ap.add_argument("--generate",action="store_true")
    args=ap.parse_args(); sizes=[int(x) for x in args.sizes.split(",") if x]; shapes=[x for x in args.shapes.split(",") if x]
    if args.generate: print(json.dumps(generate(args.base,args.public,args.secret,sizes=sizes,shapes=shapes,contracts=args.contracts),sort_keys=True))
    result=run(args.base,args.public,args.secret,args.output,provenance_limit=args.provenance_limit,provenance_encoding=args.provenance_encoding); print(json.dumps(result["summary"],sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
