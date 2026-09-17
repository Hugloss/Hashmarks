from scripts.agent_evaluation.economics import GradedRun, pareto_dominance, summarize_lane, trace_economics


def _trace(task, events):
    return {"schema":"hashmarks.agent-event-trace.v1","task_id":task,"events":events}


def test_trace_economics_joins_secret_grade_only_after_trace() -> None:
    trace=_trace("t1",[
        {"event_type":"task_received"},
        {"event_type":"work_packet","files_read":2,"bytes_read":400},
        {"event_type":"scout_requested"},
        {"event_type":"final_result","input_tokens":100,"cached_input_tokens":40,"output_tokens":20,"reasoning_tokens":10,"wall_ms":250},
    ])
    row=trace_economics(trace,GradedRun("t1",True))
    assert row["verified_solution"] is True
    assert row["model_tokens"] == 130
    assert row["cached_input_tokens"] == 40
    assert row["scout_calls"] == 1
    assert row["files_read"] == 2
    assert "expected_files" not in row


def test_trace_economics_fails_closed_on_identity_mismatch() -> None:
    try:
        trace_economics(_trace("public-task",[]),GradedRun("secret-other",True))
    except ValueError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("mismatched SECRET grade must not join")


def test_lane_summary_uses_cost_per_verified_solution() -> None:
    rows=[
        {"verified_solution":True,"model_tokens":100,"wall_ms":200.0,"scout_calls":0,"bytes_read":1000,"files_read":2},
        {"verified_solution":False,"model_tokens":50,"wall_ms":100.0,"scout_calls":1,"bytes_read":500,"files_read":1},
    ]
    value=summarize_lane("cheap-hm",rows,model="cheap",strategy="hashmarks")
    assert value["verified_rate"] == 0.5
    assert value["tokens_per_verified_solution"] == 150
    assert value["wall_ms_per_verified_solution"] == 300
    assert value["scout_calls"] == 1


def test_lane_summary_does_not_fake_missing_token_metrics() -> None:
    value=summarize_lane("unknown",[{"verified_solution":True,"model_tokens":None,"wall_ms":10.0}])
    assert value["token_metrics_available"] is False
    assert value["total_model_tokens"] is None
    assert value["tokens_per_verified_solution"] is None


def test_pareto_requires_real_token_metrics() -> None:
    lanes=[
        {"name":"cheap-hm","verified_rate":1.0,"total_model_tokens":100},
        {"name":"strong-native","verified_rate":1.0,"total_model_tokens":250},
        {"name":"unknown","verified_rate":1.0,"total_model_tokens":None},
    ]
    assert pareto_dominance(lanes) == [{"dominant":"cheap-hm","dominated":"strong-native"}]
