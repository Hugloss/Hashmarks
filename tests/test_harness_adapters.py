from scripts.agent_evaluation.adapters import CodexJsonlAdapter, GenericJsonlAdapter, adapter


def test_codex_adapter_only_translates_packet_and_events() -> None:
    a = CodexJsonlAdapter()
    packet = a.packet("fix widget", {"edit": {"path": "src/widget.py"}})
    rendered = packet.as_json()
    assert '"harness":"codex-jsonl"' in rendered
    assert 'src/widget.py' in rendered
    events = a.normalize_events(
        [
            {"type": "thread.started", "thread_id": "t-1"},
            {"type": "unknown.native.event", "payload": "ignored"},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 12, "reasoning_output_tokens": 7}},
        ],
        session_id="s1", task_id="task1", repository_identity="repo1",
    )
    assert [event["event_type"] for event in events] == ["task_received", "final_result"]
    assert events[-1]["input_tokens"] == 100
    assert events[-1]["cached_input_tokens"] == 40
    assert events[-1]["reasoning_tokens"] == 7
    assert "command" not in packet.payload


def test_generic_adapter_rejects_unknown_event_types_by_ignoring_them() -> None:
    a = GenericJsonlAdapter()
    events = a.normalize_events(
        [{"event_type": "work_packet", "actor": "opencode-adapter", "files_read": 2}, {"event_type": "made_up"}],
        session_id="s", task_id="t", repository_identity="r",
    )
    assert len(events) == 1
    assert events[0]["event_type"] == "work_packet"
    assert events[0]["actor"] == "opencode-adapter"
    assert events[0]["files_read"] == 2


def test_adapter_registry_fails_closed() -> None:
    assert adapter("codex-jsonl").name == "codex-jsonl"
    try:
        adapter("shell-executor")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown adapters must fail closed")
