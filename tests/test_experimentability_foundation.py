from scripts.agent_evaluation.experimentability import (
    EvidenceEconomics,
    ExperimentCapabilities,
    classify_decision,
    decision_trace,
    experiment_environment,
    experiment_record,
    normalize_capabilities,
    verify_experiment_record,
)


def packet(stale=False, edit=True):
    return {
        "edit": {"path": "src/owner.py"} if edit else None,
        "verify": {"path": "tests/test_owner.py"},
        "contract": None,
        "ownership_resolution": {"status": "resolved"} if edit else None,
        "verification_plan": {"available": True},
        "discrimination": {
            "needed": False,
            "reason": None,
            "candidates": [{"path": "src/owner.py"}],
        },
        "identity": {
            "repository_identity": "sha256:repo",
            "codemap_generation": 7,
            "identity_generation": 11,
            "decision_generation": "sha256:decision",
            "stale": stale,
        },
    }


def test_capabilities_bounded():
    assert (
        normalize_capabilities({"semantic_nomination": True})
        == ExperimentCapabilities(semantic_nomination=True).as_record()
    )
    try:
        normalize_capabilities({"agent_runner": True})
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported agent runner capability was accepted")


def test_environment_identity():
    e = experiment_environment(
        hashmarks_version="0.11.3",
        repository_identity="sha256:repo",
        codemap_generation=7,
        identity_generation=11,
        provider_revisions={"declared-project-links": "r3"},
        capabilities={"provenance_compression": True},
        seed=42,
        cache_state="cold",
    )
    assert e["cache_state"] == "cold" and e["environment_identity"].startswith(
        "sha256:"
    )


def test_economics():
    m = EvidenceEconomics()
    m.add("provider_calls", 2)
    m.add("graph_edges_examined", 9)
    o = m.finish(evidence={"a": 1}, refresh_ns=2_000_000, elapsed_ns=5_000_000)
    assert (
        o["provider_calls"],
        o["graph_edges_examined"],
        o["decision_latency_ms"],
        o["refresh_latency_ms"],
        o["evidence_bytes"],
    ) == (2, 9, 5.0, 2.0, 7)


def test_trace_bounded():
    t = decision_trace(packet())
    assert t["candidate_count"] == 1 and "events" not in t and "reasoning" not in t


def test_abstention_reasons():
    d = classify_decision(packet(stale=True, edit=False))
    assert (
        d["status"] == "abstained"
        and "stale_repository_evidence" in d["reasons"]
        and "no_exact_owner" in d["reasons"]
    )


def test_record_tamper_evident():
    p = packet()
    e = experiment_environment(
        hashmarks_version="0.11.3",
        repository_identity="sha256:repo",
        codemap_generation=7,
        identity_generation=11,
        cache_state="warm",
    )
    eco = EvidenceEconomics().finish(evidence=p, elapsed_ns=1)
    r = experiment_record(
        task_id="t1",
        task_identity="sha256:task",
        environment=e,
        decision_packet=p,
        economics=eco,
    )
    assert verify_experiment_record(r)
    r["task_id"] = "t2"
    assert not verify_experiment_record(r)
