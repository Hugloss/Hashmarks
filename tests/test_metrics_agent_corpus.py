import hashlib
import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.context_defaults import REPOSITORY_CONTEXT_DEFAULTS
from hashmarks.codemap.find_engine import FIND_DEFAULT_OPTIONS
from hashmarks.codemap.model import ContextDisclosure, ContextPack, SearchHit
from scripts.agent_evaluation import metrics_agent_corpus
from scripts.agent_evaluation.metrics_agent_suite import collect_suite


def test_metrics_agent_corpus_parser_owns_normal_defaults() -> None:
    parser = metrics_agent_corpus._parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(["--workspace", "/external/frozen-source"])

    assert args.workspace == Path("/external/frozen-source")
    assert args.corpus == Path(
        "benchmarks/agent_evaluation/hashmarks_342d510_retrieval_tasks.json"
    )
    assert args.budget == 1200
    assert args.limit == 20
    assert args.output is None


def test_metrics_corpus_rejects_missing_oracle_owner_before_repository_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    corpus = tmp_path / "tasks.json"
    corpus.write_text(
        json.dumps(
            {
                "schema": "hashmarks.agent-task-corpus.v1",
                "tasks": [
                    {
                        "id": "retired-owner",
                        "query": "find retired owner",
                        "expected_files": ["retired.py"],
                        "expected_symbols": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def forbidden(_workspace: Path) -> None:
        raise AssertionError("invalid corpus started repository measurement")

    monkeypatch.setattr(metrics_agent_corpus, "CodeMap", forbidden)
    with pytest.raises(ValueError, match="expected file.*retired.py"):
        metrics_agent_corpus.collect(workspace, corpus)


def test_metrics_corpus_cannot_silently_drop_a_malformed_task_row(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    corpus = tmp_path / "tasks.json"
    corpus.write_text(
        json.dumps(
            {
                "schema": "hashmarks.agent-task-corpus.v1",
                "tasks": [{"id": "valid", "query": "owner"}, None],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rows must be objects"):
        metrics_agent_corpus.collect(workspace, corpus)


@pytest.mark.parametrize("symlink", [False, True])
def test_oracle_inside_target_is_rejected_before_indexing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symlink: bool
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    corpus = workspace / "tasks.json"
    corpus.write_text(
        '{"schema":"hashmarks.agent-task-corpus.v1","tasks":['
        '{"id":"locate","query":"locate_me","expected_files":["owner.py"]}]}',
        encoding="utf-8",
    )
    (workspace / "owner.py").write_text("def locate_me(): return 1\n", encoding="utf-8")
    if symlink:
        link = tmp_path / "external-corpus.json"
        link.symlink_to(corpus)
        corpus = link

    def forbidden(_workspace: Path) -> None:
        raise AssertionError(
            "oracle-contaminated target started repository measurement"
        )

    monkeypatch.setattr(metrics_agent_corpus, "CodeMap", forbidden)
    with pytest.raises(ValueError, match="oracle corpus must be outside"):
        metrics_agent_corpus.collect(workspace, corpus)
    with pytest.raises(ValueError, match="oracle corpus must be outside"):
        collect_suite([("fixture", workspace, corpus)])


def test_suite_rejects_corpus_inside_another_target_before_first_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for workspace in (first, second):
        (workspace / "owner.py").write_text(
            "def locate_me(): return 1\n", encoding="utf-8"
        )
    payload = {
        "schema": "hashmarks.agent-task-corpus.v1",
        "tasks": [
            {
                "id": "locate",
                "query": "locate_me",
                "expected_files": ["owner.py"],
                "expected_symbols": ["locate_me"],
            }
        ],
    }
    first_corpus, second_corpus = (
        second / "first-corpus.json",
        tmp_path / "second-corpus.json",
    )
    first_corpus.write_text(json.dumps(payload), encoding="utf-8")
    second_corpus.write_text(json.dumps(payload), encoding="utf-8")

    def forbidden(_workspace: Path) -> None:
        raise AssertionError("suite began measurement before checking every oracle")

    monkeypatch.setattr(metrics_agent_corpus, "CodeMap", forbidden)
    with pytest.raises(ValueError, match="oracle corpus must be outside"):
        collect_suite(
            [("first", first, first_corpus), ("second", second, second_corpus)]
        )


def test_suite_protocol_names_the_retrieval_methods_actually_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def locate_me(): return 1\n", encoding="utf-8")
    corpus = tmp_path / "tasks.json"
    corpus.write_text(
        json.dumps(
            {
                "schema": "hashmarks.agent-task-corpus.v1",
                "tasks": [
                    {
                        "id": "locate",
                        "query": "locate_me",
                        "expected_files": ["owner.py"],
                        "expected_symbols": ["locate_me"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def observed_codemap(root: Path) -> CodeMap:
        codemap = CodeMap(root)
        find = codemap.search.find
        build = codemap.context.build
        in_context = False

        def observed_find(
            query: str, *, limit: int = FIND_DEFAULT_OPTIONS.limit
        ) -> tuple[SearchHit, ...]:
            if not in_context:
                calls.append("CodeMap.search.find")
            return find(query, limit=limit)

        def observed_build(
            query: str,
            *,
            token_budget: int = REPOSITORY_CONTEXT_DEFAULTS.token_budget,
            limit: int = REPOSITORY_CONTEXT_DEFAULTS.limit,
            disclosure: ContextDisclosure
            | str = REPOSITORY_CONTEXT_DEFAULTS.disclosure,
        ) -> ContextPack:
            nonlocal in_context
            calls.append("CodeMap.context.build")
            in_context = True
            try:
                return build(
                    query,
                    token_budget=token_budget,
                    limit=limit,
                    disclosure=disclosure,
                )
            finally:
                in_context = False

        monkeypatch.setattr(codemap.search, "find", observed_find)
        monkeypatch.setattr(codemap.context, "build", observed_build)
        return codemap

    monkeypatch.setattr(metrics_agent_corpus, "CodeMap", observed_codemap)
    result = collect_suite([("fixture", workspace, corpus)], budget=400, limit=10)
    assert calls == ["CodeMap.search.find", "CodeMap.context.build"]
    assert result["benchmark_protocol"]["retrieval"] == " + ".join(calls)
    assert result["summary"]["file_recall"] == 1.0


def test_suite_digest_binds_the_corpus_bytes_parsed_before_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def locate_me(): return 1\n", encoding="utf-8")
    corpus = tmp_path / "tasks.json"
    original = json.dumps(
        {
            "schema": "hashmarks.agent-task-corpus.v1",
            "tasks": [
                {
                    "id": "original-task",
                    "query": "locate_me",
                    "expected_files": ["owner.py"],
                    "expected_symbols": ["locate_me"],
                }
            ],
        }
    ).encode("utf-8")
    corpus.write_bytes(original)
    expected_digest = "sha256:" + hashlib.sha256(original).hexdigest()

    def mutate_after_load(root: Path) -> CodeMap:
        corpus.write_text('{"schema":"replaced-after-load"}', encoding="utf-8")
        return CodeMap(root)

    monkeypatch.setattr(metrics_agent_corpus, "CodeMap", mutate_after_load)
    result = collect_suite([("fixture", workspace, corpus)], budget=400, limit=10)
    measured = result["repositories"][0]
    assert measured["tasks"][0]["id"] == "original-task"
    assert measured["tasks"][0]["query"] == "locate_me"
    assert (
        result["benchmark_protocol"]["repositories"][0]["corpus_sha256"]
        == expected_digest
    )
    assert measured["corpus_sha256"] == expected_digest
    assert (
        "sha256:" + hashlib.sha256(corpus.read_bytes()).hexdigest() != expected_digest
    )
