import json
import threading
import time
from pathlib import Path

from hashmarks import cli
from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient


def _repo(root: Path) -> tuple[Path, str]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    return source, "change widget implementation and verify widget test"


def test_task_post_change_delta_invalidates_only_changed_revision_and_reuses_authorities(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        old_revision = previous["provenance"]["revision"]
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        delta = codemap.task_post_change_delta(
            task, ["src/owner.py"], previous_evidence=previous
        )

    assert delta["schema"] == "hashmarks.task-post-change-delta.v2"
    assert delta["change"] == "changed"
    assert delta["scope"] == "changed-paths-only"
    assert delta["consumer_owner"] == "external"
    assert "previous_index_binding" not in delta
    assert delta["path_changes"][0]["state"] == "changed"
    assert delta["path_changes"][0]["revision"] != old_revision
    assert delta["generation_after"] > delta["generation_before"]
    assert delta["invalidated"] == [
        "previous-evidence-generation",
        "candidate-source-revision",
    ]
    assert set(delta["reused"]) >= {
        "task-candidate",
        "verification-surface",
        "verification-plan",
        "selection-provenance",
    }
    assert delta["path_changes"][0]["revision"] != old_revision
    assert "replacement" not in delta
    encoded = json.dumps(delta, sort_keys=True)
    assert "edit_evidence" not in encoded
    assert "def widget" not in encoded


def test_task_post_change_delta_noop_keeps_generation_and_revision_reusable(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        source.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        delta = codemap.task_post_change_delta(
            task, ["src/owner.py"], previous_evidence=previous
        )

    assert delta["change"] == "unchanged"
    assert delta["generation_after"] == delta["generation_before"]
    assert delta["path_changes"] == [{"path": "src/owner.py", "state": "unchanged"}]
    assert delta["invalidated"] == []
    assert "candidate-source-revision" in delta["reused"]


def test_task_post_change_delta_reports_new_owner_without_replaying_unchanged_verification(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine_a.py").write_text(
        "def widget(): return 'a'\n", encoding="utf-8"
    )
    (tmp_path / "src" / "engine_b.py").write_text(
        "def widget(): return 'b'\n", encoding="utf-8"
    )
    route = tmp_path / "src" / "route.py"
    route.write_text(
        "from src.engine_a import widget\ndef route(): return widget()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_route.py").write_text(
        "from src.route import route\ndef test_route(): assert route() == 'new'\n",
        encoding="utf-8",
    )
    task = "change route widget behavior and verify route test"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        assert previous["ownership"]["candidate"]["path"] == "src/engine_a.py"
        route.write_text(
            "from src.engine_b import widget\ndef route(): return widget()\n",
            encoding="utf-8",
        )
        delta = codemap.task_post_change_delta(
            task, ["src/route.py"], previous_evidence=previous
        )

    assert (
        delta["replacement"]["ownership"]["candidate"]["path"]
        == "src/engine_b.py"
    )
    assert "task-candidate" in delta["invalidated"]
    assert "verification-surface" in delta["reused"]
    assert "verification-plan" in delta["reused"]
    assert "verification" not in delta["replacement"]


def test_task_post_change_delta_rejects_non_start_packet(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        try:
            codemap.task_post_change_delta(
                task, ["src/owner.py"], previous_evidence={"schema": "wrong"}
            )
        except ValueError as exc:
            assert "hashmarks.task-evidence.v2" in str(exc)
        else:
            raise AssertionError("invalid previous_evidence must fail closed")


def test_post_change_cli_reads_exact_previous_evidence_packet(
    tmp_path: Path, capsys
) -> None:
    source, task = _repo(tmp_path)
    previous_path = tmp_path / "previous-evidence.json"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous_path.write_text(
            json.dumps(codemap.task_evidence(task)), encoding="utf-8"
        )
    source.write_text("def widget(): return 'new'\n", encoding="utf-8")

    assert (
        cli.main(
            [
                "--workspace",
                str(tmp_path),
                "post-change",
                task,
                "--changed",
                "src/owner.py",
                "--previous-evidence",
                str(previous_path),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == "hashmarks.task-post-change-delta.v2"
    assert output["path_changes"][0]["state"] == "changed"
    assert "candidate-source-revision" in output["invalidated"]


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_service_task_post_change_delta_preserves_external_execution_owner(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    socket_path = tmp_path / "post-change.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        previous = client.task_evidence(task)
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        delta = client.task_post_change_delta(
            task, ["src/owner.py"], previous_evidence=previous
        )
        assert delta["schema"] == "hashmarks.task-post-change-delta.v2"
        assert delta["consumer_owner"] == "external"
        assert "candidate-source-revision" in delta["invalidated"]
    finally:
        client.stop()
        thread.join(timeout=5)


def test_external_evaluation_post_change_qualification_freezes_before_secret_join(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.generate_hard_agent_corpus import generate
    from scripts.agent_evaluation.score_agent_post_edit_delta import run

    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    output = tmp_path / "post-change.json"
    generate(repo, public, secret, cases_per_category=1)
    payload = run(repo, public, secret, output)

    assert payload["summary"]["tasks"] == 6
    assert payload["summary"]["fully_correct"] == 6
    assert payload["summary"]["path_change_detected"] == 6
    assert payload["summary"]["revision_invalidated"] == 6
    assert payload["summary"]["generation_invalidated"] == 6
    assert payload["summary"]["candidate_reused"] == 6
    assert payload["summary"]["verification_surface_reused"] == 6
    assert payload["summary"]["verification_plan_reused"] == 6
    assert payload["summary"]["replacement_absent"] == 6
    assert (
        payload["summary"]["delta_visible_bytes"]
        < payload["summary"]["full_refreshed_start_visible_bytes"]
    )
    assert (
        payload["protocol"][
            "secret_join_after_start_edit_delta_and_counterfactual_freeze"
        ]
        is True
    )


def test_task_post_change_delta_rejects_foreign_repository_previous_evidence(
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    source_a, task = _repo(repo_a)
    _source_b, _ = _repo(repo_b)
    with CodeMap(repo_a) as codemap_a:
        codemap_a.sync()
        previous = codemap_a.task_evidence(task)
    with CodeMap(repo_b) as codemap_b:
        codemap_b.sync()
        try:
            codemap_b.task_post_change_delta(
                task, ["src/owner.py"], previous_evidence=previous
            )
        except ValueError as exc:
            assert "repository-mismatch" in str(exc)
        else:
            raise AssertionError("foreign repository continuity must fail closed")


def test_task_post_change_delta_rejects_previous_evidence_for_other_task(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        try:
            codemap.task_post_change_delta(
                "different task", ["src/owner.py"], previous_evidence=previous
            )
        except ValueError as exc:
            assert "task-mismatch" in str(exc)
        else:
            raise AssertionError("cross-task continuity must fail closed")


def test_task_post_change_delta_rejects_tampered_context_identity(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        previous["provenance"] = dict(previous["provenance"])
        previous["provenance"]["context_identity"] = "sha256:" + "0" * 64
        try:
            codemap.task_post_change_delta(
                task, ["src/owner.py"], previous_evidence=previous
            )
        except ValueError as exc:
            assert "context-identity-mismatch" in str(exc)
        else:
            raise AssertionError("tampered evidence context must fail closed")


def test_task_post_change_delta_rejects_previous_generation_before_reuse(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        codemap.sync(["src/owner.py"])
        try:
            codemap.task_post_change_delta(
                task, ["src/owner.py"], previous_evidence=previous
            )
        except ValueError as exc:
            assert "codemap-generation-mismatch" in str(exc)
        else:
            raise AssertionError("older-generation continuity must fail closed")


def test_task_post_change_delta_rejects_unbound_previous_evidence(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        previous.pop("provenance")
        try:
            codemap.task_post_change_delta(
                task, ["src/owner.py"], previous_evidence=previous
            )
        except ValueError as exc:
            assert "bound authority receipt and provenance" in str(exc)
        else:
            raise AssertionError("unbound continuity must fail closed")
