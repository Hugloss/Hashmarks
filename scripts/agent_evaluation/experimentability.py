from __future__ import annotations
import hashlib, json, time
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from hashmarks.portable_scalar import (
    require_nonblank_string,
    require_optional_portable_nonnegative_integer,
)

EXPERIMENT_RECORD_SCHEMA="hashmarks.experiment-record.v1"
EXPERIMENT_ENVIRONMENT_SCHEMA="hashmarks.experiment-environment.v1"
EXPERIMENT_CAPABILITIES_SCHEMA="hashmarks.experiment-capabilities.v1"
_ALLOWED_CAPABILITIES=frozenset({"semantic_nomination","provenance_compression"})

def _canonical_bytes(value: object)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
def digest(value: object)->str:
    return "sha256:"+hashlib.sha256(_canonical_bytes(value)).hexdigest()

@dataclass(frozen=True)
class ExperimentCapabilities:
    semantic_nomination: bool=False
    provenance_compression: bool=False
    def as_record(self)->dict[str,Any]:
        values=asdict(self)
        return {"schema":EXPERIMENT_CAPABILITIES_SCHEMA,"values":values,"identity":digest(values)}

def normalize_capabilities(capabilities: ExperimentCapabilities|Mapping[str,bool]|None)->dict[str,Any]:
    if capabilities is None: return ExperimentCapabilities().as_record()
    if isinstance(capabilities,ExperimentCapabilities): return capabilities.as_record()
    unknown=set(capabilities)-_ALLOWED_CAPABILITIES
    if unknown: raise ValueError(f"unsupported experiment capabilities: {sorted(unknown)}")
    values={}
    for name in sorted(_ALLOWED_CAPABILITIES):
        value=capabilities.get(name,False)
        if type(value) is not bool:
            raise ValueError(f"experiment capability {name} must be a boolean")
        values[name]=value
    return {"schema":EXPERIMENT_CAPABILITIES_SCHEMA,"values":values,"identity":digest(values)}

def experiment_environment(*,hashmarks_version:str,repository_identity:str|None,codemap_generation:int|None,
 identity_generation:int|None,provider_revisions:Mapping[str,str]|None=None,
 capabilities:ExperimentCapabilities|Mapping[str,bool]|None=None,seed:int|None=None,cache_state:str="unknown")->dict[str,Any]:
    if cache_state not in {"cold","warm","incremental","repeat","unknown"}: raise ValueError("unsupported experiment cache_state")
    hashmarks_version=require_nonblank_string(hashmarks_version,field="hashmarks_version")
    repository_identity=require_nonblank_string(repository_identity,field="repository_identity",optional=True)
    codemap_generation=require_optional_portable_nonnegative_integer(codemap_generation,field="codemap_generation")
    identity_generation=require_optional_portable_nonnegative_integer(identity_generation,field="identity_generation")
    seed=require_optional_portable_nonnegative_integer(seed,field="seed")
    revisions={}
    for key,value in (provider_revisions or {}).items():
        clean_key=require_nonblank_string(key,field="provider revision provider")
        clean_value=require_nonblank_string(value,field=f"provider revision {clean_key}")
        revisions[clean_key]=clean_value
    payload={"schema":EXPERIMENT_ENVIRONMENT_SCHEMA,"hashmarks_version":hashmarks_version,
     "repository_identity":repository_identity,"codemap_generation":codemap_generation,"identity_generation":identity_generation,
     "provider_revisions":dict(sorted(revisions.items())),"capabilities":normalize_capabilities(capabilities),
     "seed":seed,"cache_state":cache_state}
    payload["environment_identity"]=digest(payload); return payload

class EvidenceEconomics:
    """Bounded counters for Hashmarks evidence work; never model reasoning/execution."""
    def __init__(self)->None:
        self.started_ns=time.perf_counter_ns()
        self.counters={"provider_calls":0,"database_lookups":0,"candidates_examined":0,"graph_edges_examined":0,
                       "evidence_items_considered":0,"evidence_items_emitted":0}
    def add(self,name:str,amount:int=1)->None:
        if name not in self.counters: raise ValueError(f"unsupported evidence economics counter: {name}")
        if amount<0: raise ValueError("counter increments must be non-negative")
        self.counters[name]+=amount
    def finish(self,*,evidence:object,refresh_ns:int|None=None,elapsed_ns:int|None=None)->dict[str,Any]:
        duration=max(0,elapsed_ns if elapsed_ns is not None else time.perf_counter_ns()-self.started_ns)
        return {**self.counters,"decision_latency_ns":duration,"decision_latency_ms":duration/1_000_000,
                "refresh_latency_ns":refresh_ns,"refresh_latency_ms":None if refresh_ns is None else refresh_ns/1_000_000,
                "evidence_bytes":len(_canonical_bytes(evidence))}

def classify_decision(packet:Mapping[str,Any])->dict[str,Any]:
    edit=packet.get("edit"); discrimination=packet.get("discrimination"); identity=packet.get("identity")
    ownership=packet.get("ownership_resolution"); reasons=[]
    if isinstance(identity,Mapping) and identity.get("stale") is True: reasons.append("stale_repository_evidence")
    if not isinstance(edit,Mapping) or not edit.get("path"): reasons.append("no_exact_owner")
    if isinstance(discrimination,Mapping) and discrimination.get("needed"):
        reason=str(discrimination.get("reason") or "")
        reasons.append("ambiguous_owner" if "ambig" in reason else reason.replace(" ","_"))
    if isinstance(ownership,Mapping):
        status=str(ownership.get("status") or ownership.get("reason") or "")
        if status and status!="resolved" and status not in reasons: reasons.append(status.replace(" ","_"))
    return {"status":"resolved" if isinstance(edit,Mapping) and edit.get("path") and not reasons else "abstained","reasons":reasons}

def decision_trace(packet:Mapping[str,Any])->dict[str,Any]:
    identity=packet.get("identity") if isinstance(packet.get("identity"),Mapping) else {}
    discrimination=packet.get("discrimination") if isinstance(packet.get("discrimination"),Mapping) else {}
    candidates=discrimination.get("candidates") if isinstance(discrimination.get("candidates"),list) else []; emitted=[]
    for key in ("edit","verify","contract"):
        row=packet.get(key)
        if isinstance(row,Mapping) and row.get("path"): emitted.append({"role":key,"path":str(row["path"])})
    return {"schema":"hashmarks.experiment-decision-trace.v1","decision_generation":identity.get("decision_generation"),
     "repository_identity":identity.get("repository_identity"),"codemap_generation":identity.get("codemap_generation"),
     "identity_generation":identity.get("identity_generation"),"classification":classify_decision(packet),
     "candidate_count":len(candidates),"emitted":emitted,"authority_sources":{"ownership_resolution":bool(packet.get("ownership_resolution")),
     "verification_plan":bool(packet.get("verification_plan"))}}

def experiment_record(*,task_id:str,task_identity:str,environment:Mapping[str,Any],decision_packet:Mapping[str,Any],
 economics:Mapping[str,Any])->dict[str,Any]:
    if environment.get("schema")!=EXPERIMENT_ENVIRONMENT_SCHEMA: raise ValueError("unsupported experiment environment schema")
    payload={"schema":EXPERIMENT_RECORD_SCHEMA,"task_id":task_id,"task_identity":task_identity,
     "environment_identity":environment.get("environment_identity"),"environment":dict(environment),
     "decision":decision_trace(decision_packet),"economics":dict(economics),"decision_packet_identity":digest(decision_packet)}
    payload["record_identity"]=digest(payload); return payload
def verify_experiment_record(record:Mapping[str,Any])->bool:
    if record.get("schema")!=EXPERIMENT_RECORD_SCHEMA: return False
    claimed=record.get("record_identity"); payload=dict(record); payload.pop("record_identity",None)
    return isinstance(claimed,str) and claimed==digest(payload)
