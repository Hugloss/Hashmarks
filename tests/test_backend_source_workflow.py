"""Selected source lines retain byte, transport and independent replay proof."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation import backend_source
from scripts.repository_evaluation.backend_corpus import SCHEMA, load_corpus
from scripts.repository_evaluation.backend_regrading import (
    regrade_task_workflow,
    verify_task_summary,
)
from scripts.repository_evaluation.common import GRADER_SCHEMA, write_json
from scripts.repository_evaluation.run_backend import run_backend

Corpus = tuple[Path, dict[str, Path]]
Observed = tuple[Corpus, Path, dict[str, object]]


@pytest.fixture(scope="module")
def source_corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    base = tmp_path_factory.mktemp("source-line-corpus")
    sources, definitions, labels, requests, oracles = {}, {}, {}, {}, {}
    for stage, field in (("before", "old_name"), ("after", "new_name")):
        root = base / stage
        root.mkdir()
        file = root / "backend.py"
        line = f'WIRE = declared_provider(kind="{field}")'
        text = (
            'raise RuntimeError("repository source must not execute")\n'
            + line
            + "\ndef handler():\n    return WIRE\n"
        )
        file.write_text(text)
        sources[stage] = root
        definitions[stage] = {
            "repository": "controlled-source",
            "content_identity": repository_content_identity(root),
        }
        labels[stage] = [
            {
                "path": "backend.py",
                "symbol": "handler",
                "start_line": 3,
                "end_line": 4,
                "sha256": hashlib.sha256(
                    b"".join(file.read_bytes().splitlines(True)[2:])
                ).hexdigest(),
            }
        ]
        digest = hashlib.sha256(
            b"hashmarks.source-line.v1\0" + line.encode()
        ).hexdigest()
        checks = [
            {
                "id": "exact-source-line",
                "pointer": "/line_anchors/*",
                "predicate": "includes_scoped_record",
                "support": "supported",
                "value": {
                    "scope": {"line": 2, "state": "observed", "line_sha256": digest},
                    "pointer": "/context_excerpt/*",
                    "record": {
                        "line": 2,
                        "role": "anchor",
                        "text": line,
                        "truncated_left": False,
                        "truncated_right": False,
                    },
                },
            },
            {
                "id": "observer-only",
                "pointer": "/authority",
                "predicate": "equals",
                "value": "repository-evidence-only",
                "authority_check": True,
            },
            {
                "id": "no-execution",
                "pointer": "/execution_effect",
                "predicate": "equals",
                "value": "none",
                "authority_check": True,
            },
        ]
        requests[stage] = {
            "paths": ["backend.py"],
            "result_mode": "member",
            "context_lines": {"lines": [2], "radius": 1},
        }
        oracles[stage] = {
            "source": stage,
            "source_labels": [
                {
                    "path": "backend.py",
                    "start_line": 2,
                    "end_line": 2,
                    "sha256": hashlib.sha256((line + "\n").encode()).hexdigest(),
                }
            ],
            "checks": checks,
            "display_checks": {
                format: [{**checks[0], "pointer": "/groups/*/findings/*/details"}]
                for format in ("structured", "compact", "text")
            },
        }
    workflow = {
        "id": "handler",
        "repository": "controlled-source",
        "problem_id": "declared-wiring",
        "task": "Inspect declared wiring in backend.py",
        "before": "before",
        "after": "after",
        "capabilities": [11],
        "changed_paths": ["backend.py"],
        "transitions": [
            {"kind": "modify", "before_path": "backend.py", "after_path": "backend.py"}
        ],
        "source_observations": requests,
    }
    rule = {
        "expected_owner_path": "backend.py",
        "source_labels": labels,
        "source_oracles": oracles,
        "checks": [
            {
                "id": "source-visible",
                "pointer": "/retrieval/results/*",
                "predicate": "includes_record",
                "value": {"path": "backend.py"},
            }
        ],
        "delta_checks": [
            {
                "id": "current-revision",
                "pointer": "/path_changes/*/revision",
                "predicate": "includes",
                "value": hash_file(
                    sources["after"] / "backend.py", domain=FILE_DOMAIN
                ).hash,
            }
        ],
    }
    path = base / "suite.json"
    write_json(
        path,
        {
            "schema": SCHEMA,
            "suite": "controlled-source-lines",
            "sources": definitions,
            "grader_file": "grader.json",
            "workflows": [workflow],
        },
    )
    write_json(
        base / "grader.json", {"schema": GRADER_SCHEMA, "cases": {"handler": rule}}
    )
    return path, sources


def _admitted(corpus: Corpus) -> tuple[dict[str, object], dict[str, object]]:
    suite, grader = load_corpus(*corpus)
    return assert_object(suite["workflows"][0]), assert_object(
        grader["cases"]["handler"]
    )


@pytest.fixture(scope="module")
def observed_source(
    source_corpus: Corpus, tmp_path_factory: pytest.TempPathFactory
) -> Observed:
    suite, sources = source_corpus
    output = tmp_path_factory.mktemp("observed-source-lines")
    report = run_backend(sources=sources, suite_path=suite, output_dir=output)
    return (
        source_corpus,
        output / "handler/observations",
        assert_object(report["outcomes"][0]),
    )


@pytest.mark.host_mcp_sdk
def test_source_lines_have_native_and_display_witnesses(
    observed_source: Observed,
) -> None:
    _, _, outcome = observed_source
    for component in assert_object(outcome["source_observations"]).values():
        assert all(
            value is True
            for value in assert_object(assert_object(component)["gates"]).values()
        )
    rows = [
        r
        for r in assert_records(outcome["gate_witnesses"])
        if str(r["gate"]).startswith("source_")
    ]
    assert {r["surface"] for r in rows} == {"api", "cli", "mcp"}
    assert {r["gate"] for r in rows} == {"source_facts", "source_presentation"}
    assert rows and all(r["state"] == "PASS" and r["artifact_sha256"] for r in rows)


@pytest.mark.host_mcp_sdk
def test_source_regrade_never_constructs_observers_or_processes(
    observed_source: Observed, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, root, outcome = observed_source
    workflow, rule = _admitted(corpus)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("pure source replay attempted observation")

    monkeypatch.setattr(backend_source, "CodeMap", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    verify_task_summary(root, workflow, rule, corpus[1], outcome)


@pytest.mark.host_mcp_sdk
@pytest.mark.parametrize(
    "mutation",
    ["text", "line-digest", "revision", "requested-line", "missing-api", "missing-mcp"],
)
def test_source_replay_rejects_missing_and_tampered_evidence(
    observed_source: Observed, tmp_path: Path, mutation: str
) -> None:
    corpus, original, outcome = observed_source
    root = tmp_path / "observations"
    shutil.copytree(original, root)
    path = root / "before/source/api.json"
    if mutation == "missing-api":
        path.unlink()
    elif mutation == "missing-mcp":
        write_json(root / "before/source/mcp.json", [])
    else:
        packet = assert_object(json.loads(path.read_bytes()))
        anchor = assert_records(packet["line_anchors"])[0]
        if mutation == "text":
            center = next(
                r
                for r in assert_records(anchor["context_excerpt"])
                if r["role"] == "anchor"
            )
            center["text"] = "wrong-source"
        elif mutation == "line-digest":
            anchor["line_sha256"] = "wrong-digest"
        elif mutation == "requested-line":
            packet["requested_lines"] = [3]
        else:
            assert_object(packet["member"])["member_revision"] = "wrong-revision"
        write_json(path, packet)
    workflow, rule = _admitted(corpus)
    with pytest.raises(ValueError):
        verify_task_summary(root, workflow, rule, corpus[1], outcome)
    if mutation == "missing-mcp":
        assert (
            assert_object(
                regrade_task_workflow(root, workflow, rule, corpus[1])["gates"]
            )["mcp"]
            is None
        )


@pytest.mark.parametrize("state", ["deny", "outline", "stale"])
def test_source_qualification_cannot_admit_unavailable_or_changed_bytes(
    source_corpus: Corpus, tmp_path: Path, state: str
) -> None:
    source = tmp_path / "source"
    shutil.copytree(source_corpus[1]["before"], source)
    _, rule = _admitted(source_corpus)
    oracle = assert_object(assert_object(rule["source_oracles"])["before"])
    if state != "stale":
        (source / ".hashmarks-context.toml").write_text(
            f'[[rule]]\npattern = "backend.py"\nvisibility = "{state}"\n'
        )
    with CodeMap(source) as codemap:
        codemap.index.sync()
        if state == "stale":
            (source / "backend.py").write_text('WIRE = "changed"\n')
        packet = codemap.source.observe(
            "backend.py", lines=(2,), anchor_context_lines=1
        )
    graded = backend_source.grade_source(source, packet, oracle)
    assert graded["revision"] is False
    assert graded["facts"] is not True
    assert packet["negative_evidence"] == "not-admissible"
    assert packet["line_anchors"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-input",
        "bool-line",
        "duplicate-line",
        "wrong-source",
        "label",
        "stage",
        "display",
    ],
)
def test_source_admission_rejects_unbound_scope(
    source_corpus: Corpus, tmp_path: Path, mutation: str
) -> None:
    suite, sources = source_corpus
    manifest = copy.deepcopy(assert_object(json.loads(suite.read_bytes())))
    grader = copy.deepcopy(
        assert_object(json.loads((suite.parent / "grader.json").read_bytes()))
    )
    workflow = assert_object(assert_array(manifest["workflows"])[0])
    requests = assert_object(workflow["source_observations"])
    request = assert_object(requests["before"])
    oracle = assert_object(
        assert_object(assert_object(grader["cases"])["handler"])["source_oracles"]
    )
    before = assert_object(oracle["before"])
    if mutation == "extra-input":
        request["argv"] = ["python", "backend.py"]
    elif mutation == "bool-line":
        assert_object(request["context_lines"])["lines"] = [True]
    elif mutation == "duplicate-line":
        assert_object(request["context_lines"])["lines"] = [2, 2]
    elif mutation == "wrong-source":
        before["source"] = "after"
    elif mutation == "label":
        assert_records(before["source_labels"])[0]["sha256"] = "wrong"
    elif mutation == "stage":
        requests.pop("after")
    else:
        assert_object(before["display_checks"]).pop("compact")
    write_json(tmp_path / "suite.json", manifest)
    write_json(tmp_path / "grader.json", grader)
    with pytest.raises(ValueError):
        load_corpus(tmp_path / "suite.json", sources)
