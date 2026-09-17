import json
from pathlib import Path
import pytest
from scripts.agent_evaluation.experiment import ExperimentLane,experiment_manifest,import_native_run,load_jsonl


def test_manifest_is_public_metadata_not_secret_answers() -> None:
 lanes=[ExperimentLane('cheap-native','codex-jsonl','cheap','native','low'),ExperimentLane('cheap-hm','codex-jsonl','cheap','hashmarks','low')]
 value=experiment_manifest(corpus_identity='sha256:corpus',lanes=lanes,secret_identity='sha256:secret')
 assert value['schema']=='hashmarks.agent-experiment-manifest.v1'
 assert value['secret_identity']=='sha256:secret'
 assert 'expected_files' not in json.dumps(value)
 assert value['lanes'][1]['strategy']=='hashmarks'
 assert value['manifest_identity'].startswith('sha256:')


def test_manifest_rejects_duplicate_lane_names() -> None:
 lane=ExperimentLane('same','generic-jsonl','m','native')
 with pytest.raises(ValueError,match='unique'):
  experiment_manifest(corpus_identity='x',lanes=[lane,lane])


def test_lane_fails_closed_on_unknown_harness() -> None:
 with pytest.raises(ValueError,match='unsupported harness adapter'):
  ExperimentLane('x','magic-shell-agent','m','native')


def test_import_codex_native_jsonl_is_deterministic(tmp_path: Path) -> None:
 p=tmp_path/'events.jsonl';p.write_text('\n'.join([json.dumps({'type':'thread.started','thread_id':'abc'}),json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12}})])+'\n')
 lane=ExperimentLane('cheap-native','codex-jsonl','cheap','native','low')
 a=import_native_run(lane=lane,task_id='t1',session_id='s1',repository_identity='repo',event_path=p)
 b=import_native_run(lane=lane,task_id='t1',session_id='s1',repository_identity='repo',event_path=p)
 assert a==b
 assert a['native_event_count']==2 and a['normalized_event_count']==2
 assert a['trace']['events'][-1]['input_tokens']==10
 assert a['trace_identity'].startswith('sha256:')


def test_invalid_jsonl_fails_with_line_number(tmp_path: Path) -> None:
 p=tmp_path/'bad.jsonl';p.write_text('{}\nnot-json\n')
 with pytest.raises(ValueError,match='line 2'):
  load_jsonl(p)


def _bundle(lane: str, task: str):
    return {"schema":"hashmarks.agent-experiment-bundle.v1","lane":{"name":lane},"trace":{"task_id":task}}


def test_coverage_ledger_fails_closed_on_missing_lane_task() -> None:
    from scripts.agent_evaluation.experiment import coverage_ledger, require_complete_coverage
    manifest=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native'),ExperimentLane('hm','generic-jsonl','m','hashmarks')])
    ledger=coverage_ledger(manifest=manifest,task_ids=['t1','t2'],bundles=[_bundle('native','t1'),_bundle('native','t2'),_bundle('hm','t1')])
    assert ledger['expected_runs']==4 and ledger['observed_runs']==3
    assert ledger['complete'] is False
    assert ledger['missing']==[{'lane':'hm','task_id':'t2'}]
    with pytest.raises(ValueError,match='incomplete'):
        require_complete_coverage(ledger)


def test_coverage_ledger_rejects_duplicates_and_unexpected_runs() -> None:
    from scripts.agent_evaluation.experiment import coverage_ledger
    manifest=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native')])
    ledger=coverage_ledger(manifest=manifest,task_ids=['t1'],bundles=[_bundle('native','t1'),_bundle('native','t1'),_bundle('other','t1')])
    assert ledger['complete'] is False
    assert ledger['duplicates']==[{'lane':'native','task_id':'t1'}]
    assert ledger['invalid']==['unexpected:other:t1']


def test_coverage_ledger_can_certify_exact_matrix() -> None:
    from scripts.agent_evaluation.experiment import coverage_ledger, require_complete_coverage
    manifest=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native'),ExperimentLane('hm','generic-jsonl','m','hashmarks')])
    bundles=[_bundle(l,t) for l in ('native','hm') for t in ('t1','t2')]
    ledger=coverage_ledger(manifest=manifest,task_ids=['t1','t2'],bundles=bundles)
    assert ledger['complete'] is True and ledger['observed_runs']==4
    require_complete_coverage(ledger)


def _trace_bundle(lane: str, task: str, tokens: int, wall: float):
    return {
        "schema":"hashmarks.agent-experiment-bundle.v1",
        "lane":{"name":lane},
        "trace":{"schema":"hashmarks.agent-event-trace.v1","task_id":task,"events":[{"event_type":"final_result","input_tokens":tokens,"wall_ms":wall}]},
    }


def test_report_requires_complete_coverage_before_secret_join() -> None:
    from scripts.agent_evaluation.experiment import assemble_experiment_report
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native'),ExperimentLane('hm','generic-jsonl','m','hashmarks')])
    with pytest.raises(ValueError,match='coverage is incomplete'):
        assemble_experiment_report(manifest=m,task_ids=['t1'],bundles=[_trace_bundle('native','t1',10,20)],grades={'t1':True})


def test_report_rejects_secret_grade_task_set_mismatch() -> None:
    from scripts.agent_evaluation.experiment import assemble_experiment_report
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native')])
    with pytest.raises(ValueError,match='SECRET grade task set mismatch'):
        assemble_experiment_report(manifest=m,task_ids=['t1'],bundles=[_trace_bundle('native','t1',10,20)],grades={'other':True})


def test_report_emits_verified_cost_and_pareto_without_answer_key() -> None:
    from scripts.agent_evaluation.experiment import assemble_experiment_report
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','strong','native'),ExperimentLane('hm','generic-jsonl','cheap','hashmarks')])
    bundles=[_trace_bundle('native','t1',100,100),_trace_bundle('hm','t1',40,80)]
    r=assemble_experiment_report(manifest=m,task_ids=['t1'],bundles=bundles,grades={'t1':True})
    assert r['complete'] is True
    by={row['name']:row for row in r['lanes']}
    assert by['native']['tokens_per_verified_solution']==100
    assert by['hm']['tokens_per_verified_solution']==40
    assert {'dominant':'hm','dominated':'native'} in r['pareto_dominance']
    text=json.dumps(r)
    assert 'expected_files' not in text and 'expected_symbols' not in text


def _cert_bundle(lane: str, task: str, trace_identity: str, native_identity: str):
    return {"schema":"hashmarks.agent-experiment-bundle.v1","lane":{"name":lane},"trace":{"schema":"hashmarks.agent-event-trace.v1","task_id":task,"events":[]},"trace_identity":trace_identity,"native_event_sha256":native_identity}


def test_experiment_certificate_binds_manifest_traces_secret_and_report() -> None:
    from scripts.agent_evaluation.experiment import experiment_certificate,verify_experiment_certificate
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native')])
    bundles=[_cert_bundle('native','t1','sha256:trace','sha256:native')]
    report={"schema":"hashmarks.agent-experiment-report.v1","complete":True,"manifest_identity":m['manifest_identity'],"coverage":{"complete":True},"lanes":[]}
    cert=experiment_certificate(manifest=m,bundles=bundles,report=report,secret_identity='sha256:secret')
    assert cert['certificate_identity'].startswith('sha256:')
    assert cert['secret_identity']=='sha256:secret'
    assert verify_experiment_certificate(certificate=cert,manifest=m,bundles=bundles,report=report,secret_identity='sha256:secret') is True
    assert 'expected_files' not in json.dumps(cert)


def test_experiment_certificate_detects_report_tampering() -> None:
    from scripts.agent_evaluation.experiment import experiment_certificate,verify_experiment_certificate
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native')])
    bundles=[_cert_bundle('native','t1','sha256:trace','sha256:native')]
    report={"schema":"hashmarks.agent-experiment-report.v1","complete":True,"manifest_identity":m['manifest_identity'],"coverage":{"complete":True},"lanes":[]}
    cert=experiment_certificate(manifest=m,bundles=bundles,report=report,secret_identity='sha256:secret')
    changed=dict(report);changed['lanes']=[{'name':'forged'}]
    assert verify_experiment_certificate(certificate=cert,manifest=m,bundles=bundles,report=changed,secret_identity='sha256:secret') is False


def test_experiment_certificate_refuses_incomplete_report_and_unsealed_bundle() -> None:
    from scripts.agent_evaluation.experiment import experiment_certificate
    m=experiment_manifest(corpus_identity='c',lanes=[ExperimentLane('native','generic-jsonl','m','native')])
    with pytest.raises(ValueError,match='complete experiment report'):
        experiment_certificate(manifest=m,bundles=[],report={"schema":"hashmarks.agent-experiment-report.v1","complete":False,"manifest_identity":m['manifest_identity']},secret_identity='sha256:secret')
    with pytest.raises(ValueError,match='trace identity'):
        experiment_certificate(manifest=m,bundles=[{"schema":"hashmarks.agent-experiment-bundle.v1","trace_identity":None,"native_event_sha256":"sha256:n"}],report={"schema":"hashmarks.agent-experiment-report.v1","complete":True,"manifest_identity":m['manifest_identity']},secret_identity='sha256:secret')
