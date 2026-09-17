from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def cobalt_value() -> str:\n    return 'old'\n", encoding="utf-8"
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import cobalt_value\n\n"
        "def test_cobalt_value():\n    assert cobalt_value() == 'new'\n",
        encoding="utf-8",
    )


def _task() -> str:
    return "Change cobalt_value from old to new and verify cobalt_value"


def test_task_evidence_exposes_compact_selection_source_revision_and_unknown_freshness(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(_task(), token_budget=512)

    with CodeMap(tmp_path) as codemap:
        expected = str(codemap.store.file_row("src/engine.py")["file_digest"])
    provenance = start["provenance"]
    assert provenance["why"] == "structural-import"
    assert provenance["revision"] == expected
    assert provenance["freshness"] == "unknown"
    assert "generation" not in provenance
    assert "freshness_reason" not in provenance


def test_task_evidence_maps_generation_bound_continuity_to_proven(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()
        monkeypatch.setattr(
            codemap, "_generation_status", lambda: (generation, 71, False)
        )
        start = codemap.task_evidence(_task(), token_budget=512)

    provenance = start["provenance"]
    assert provenance["freshness"] == "proven"
    assert "identity_generation" not in provenance
    assert "freshness_reason" not in provenance


def test_task_evidence_reports_stale_when_continuity_reports_change(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()
        monkeypatch.setattr(
            codemap, "_generation_status", lambda: (generation, 72, True)
        )
        start = codemap.task_evidence(_task(), token_budget=512)

    assert start["status"] == "safe-stale"
    assert start["provenance"]["freshness"] == "stale"
    assert start["provenance"]["freshness_reason"] == "continuity-reported-change"


def test_task_evidence_marks_action_stale_if_selected_source_refresh_changes_generation(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap._task_evidence_evidence_item

        def mutate_then_project(row, *, role, token_budget, task=""):
            path = tmp_path / str(row["path"])
            path.write_text(
                path.read_text(encoding="utf-8") + "# changed during packet\n",
                encoding="utf-8",
            )
            return original(row, role=role, token_budget=token_budget, task=task)

        monkeypatch.setattr(
            codemap, "_task_evidence_evidence_item", mutate_then_project
        )
        start = codemap.task_evidence(_task(), token_budget=512)

    assert start["status"] == "safe-stale"
    provenance = start["provenance"]
    assert provenance["freshness"] == "stale"
    assert provenance["freshness_reason"] == "generation-changed-during-start"
    assert provenance["selection_generation"] < provenance["generation"]


def test_config_projection_provenance_stays_post_selection(tmp_path: Path) -> None:
    from scripts.agent_evaluation.generate_hard_agent_corpus import generate

    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    generate(repo, public, secret, cases_per_category=1)
    import json

    tasks = json.loads(public.read_text(encoding="utf-8"))["tasks"]
    task = next(row for row in tasks if row["id"] == "hard-004")
    with CodeMap(repo) as codemap:
        codemap.sync()
        start = codemap.task_evidence(task["query"], token_budget=512)

    assert start["edit"].endswith("policy.toml")
    assert start["edit_evidence"]["representation"] == "config-key-range"
    assert start["provenance"]["why"] == "contract-authority"
    assert len(start["provenance"]["revision"]) == 64


def test_task_evidence_context_identity_is_budget_independent_and_revision_bound(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        starts = [
            codemap.task_evidence(_task(), token_budget=budget)
            for budget in (1, 32, 512)
        ]
        identities = {str(start["provenance"]["context_identity"]) for start in starts}
        assert len(identities) == 1
        assert next(iter(identities)).startswith("sha256:")

        (tmp_path / "src" / "engine.py").write_text(
            "def cobalt_value() -> str:\n    return 'new-revision'\n", encoding="utf-8"
        )
        codemap.sync()
        changed = codemap.task_evidence(_task(), token_budget=32)
    assert changed["provenance"]["context_identity"] not in identities


def test_task_evidence_context_identity_changes_with_freshness_authority(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        unknown = codemap.task_evidence(_task(), token_budget=32)
        generation = codemap.store.generation()
        monkeypatch.setattr(
            codemap, "_generation_status", lambda: (generation, 91, False)
        )
        proven = codemap.task_evidence(_task(), token_budget=32)
    assert unknown["provenance"]["freshness"] == "unknown"
    assert proven["provenance"]["freshness"] == "proven"
    assert (
        unknown["provenance"]["context_identity"]
        != proven["provenance"]["context_identity"]
    )


def test_task_evidence_marks_stale_when_selected_verification_contents_change_after_sync(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        (tmp_path / "tests" / "test_engine.py").write_text(
            "def test_unrelated():\n    assert True\n", encoding="utf-8"
        )
        start = codemap.task_evidence(_task(), token_budget=512)
    assert start["status"] == "safe-stale"
    assert start["verify_path"] == "tests/test_engine.py"
    assert start["provenance"]["freshness"] == "stale"
    assert (
        start["provenance"]["freshness_reason"]
        == "verification-changed-since-selection"
    )


def test_task_evidence_marks_stale_when_selected_verification_is_deleted_after_sync(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        (tmp_path / "tests" / "test_engine.py").unlink()
        start = codemap.task_evidence(_task(), token_budget=512)
    assert start["status"] == "safe-stale"
    assert (
        start["provenance"]["freshness_reason"]
        == "verification-changed-since-selection"
    )


def test_task_evidence_marks_stale_when_selected_verification_is_renamed_after_sync(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        (tmp_path / "tests" / "test_engine.py").rename(
            tmp_path / "tests" / "test_engine_renamed.py"
        )
        start = codemap.task_evidence(_task(), token_budget=512)
    assert start["status"] == "safe-stale"
    assert (
        start["provenance"]["freshness_reason"]
        == "verification-changed-since-selection"
    )


def test_task_evidence_closing_fence_catches_verification_mutation_during_packet_projection(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap._task_evidence_evidence_item

        def mutate_verification_then_project(row, *, role, token_budget, task=""):
            (tmp_path / "tests" / "test_engine.py").write_text(
                "def test_replaced():\n    assert True\n", encoding="utf-8"
            )
            return original(row, role=role, token_budget=token_budget, task=task)

        monkeypatch.setattr(
            codemap, "_task_evidence_evidence_item", mutate_verification_then_project
        )
        start = codemap.task_evidence(_task(), token_budget=512)
    assert start["status"] == "safe-stale"
    assert (
        start["provenance"]["freshness_reason"]
        == "verification-changed-since-selection"
    )
