from pathlib import Path

def test_internal_agent_scripts_present_and_secret_join_is_separate():
    ledger=Path('scripts/agent_evaluation/internal_agent_ledger.py').read_text()
    grader=Path('scripts/agent_evaluation/grade_internal_agent_runs.py').read_text()
    assert '--secret' not in ledger
    assert '--secret' in grader
    assert "st['sealed']=True" in ledger
    assert 'secret_join_after_trace_seal' in grader
