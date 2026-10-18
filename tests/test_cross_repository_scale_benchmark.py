import json
from pathlib import Path

import pytest

from scripts.score_cross_repository_scale import generate, run


def test_scale_generator_separates_public_and_secret(tmp_path: Path) -> None:
    base = tmp_path / "repos"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    manifest = generate(
        base, public, secret, sizes=[10], shapes=["diamond"], contracts=2
    )
    pub = json.loads(public.read_text())
    sec = json.loads(secret.read_text())
    assert manifest["answer_key_inside_worker_repo"] is False
    assert pub["schema"] == "hashmarks.cross-repository-scale-public.v1"
    assert sec["schema"] == "hashmarks.cross-repository-scale-secret.v1"
    assert "depths" not in pub["tasks"][0] and "depths" in sec["tasks"][0]


def test_scale_measurement_exposes_provenance_limit_without_hiding_project_recall(
    tmp_path: Path,
) -> None:
    base = tmp_path / "repos"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    output = tmp_path / "out.json"
    generate(base, public, secret, sizes=[10], shapes=["fanout"], contracts=1)
    result = run(base, public, secret, output, provenance_limit=6)
    source = next(row for row in result["rows"] if row["kind"] == "source")
    assert source["project_recall"] == 1.0
    assert source["reported_provenance_rows"] == 6
    assert source["provenance_recall"] < 1.0
    assert result["protocol"]["secret_join_after_packet_freeze"] is True


@pytest.mark.parametrize(
    ("shape", "depths"),
    [
        ("chain", [1, 2, 3, 4]),
        ("fanout", [1, 1, 1, 1]),
        ("fanin", [1, 1, 1, 2]),
        ("diamond", [1, 1, 2, 3]),
    ],
)
def test_scale_generator_preserves_graph_reachability(
    tmp_path: Path, shape: str, depths: list[int]
) -> None:
    base = tmp_path / "repos"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"

    generate(base, public, secret, sizes=[5], shapes=[shape], contracts=1)

    tasks = json.loads(secret.read_text())["tasks"]
    source = tasks[0]
    assert source["depths"] == {
        f"npm:@scale/p{index:04d}": depth for index, depth in enumerate(depths, start=1)
    }
    assert (
        len(source["edges"])
        == {"chain": 4, "fanout": 4, "fanin": 6, "diamond": 5}[shape]
    )


def test_scale_generator_replaces_existing_corpus_and_rejects_unknown_shape(
    tmp_path: Path,
) -> None:
    base = tmp_path / "repos"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    generate(base, public, secret, sizes=[1], shapes=["chain"], contracts=1)
    stale = base / "stale.txt"
    stale.write_text("obsolete", encoding="utf-8")

    generate(base, public, secret, sizes=[1], shapes=["fanout"], contracts=1)

    assert not stale.exists()
    with pytest.raises(ValueError, match="unknown"):
        generate(base, public, secret, sizes=[2], shapes=["unknown"], contracts=1)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing",
        "all-missing",
        "duplicate",
        "invented",
        "wrong-kind",
        "wrong-producer",
    ],
)
def test_scale_success_requires_exact_explicit_relationships(
    mutation: str | None,
) -> None:
    from scripts.score_cross_repository_scale import _score_frozen_packet

    edges = [
        {
            "from": "client",
            "to": "root",
            "kind": "api",
            "producer": "declared-project-links",
        },
        {
            "from": "client",
            "to": "root",
            "kind": "contract",
            "producer": "declared-project-links",
        },
    ]
    expected = {
        "projects": ["client"],
        "depths": {"client": 1},
        "edges": [["client", "root", "api"], ["client", "root", "contract"]],
    }
    if mutation == "missing":
        edges.pop()
    elif mutation == "all-missing":
        edges.clear()
    elif mutation == "duplicate":
        edges.append(dict(edges[0]))
    elif mutation == "invented":
        edges.append(
            {
                "from": "client",
                "to": "unrelated",
                "kind": "api",
                "producer": "declared-project-links",
            }
        )
    elif mutation == "wrong-kind":
        edges[1]["kind"] = "other"
    elif mutation == "wrong-producer":
        edges[1]["producer"] = "unqualified"
    item = {
        "task": {
            "id": "explicit-pair",
            "shape": "parallel",
            "projects": 2,
            "kind": "source",
        },
        "packet": {
            "projects": ["client"],
            "project_impact": {
                "affected": [{"project": "client", "depth": 1}],
                "edges": edges,
            },
        },
        "record": {
            "economics": {"evidence_bytes": 1, "decision_latency_ms": 1},
            "record_identity": "fixture",
        },
        "setup_ms": 1,
    }
    result = _score_frozen_packet(item, expected)
    assert (
        result["project_recall"]
        == result["project_precision"]
        == result["provenance_recall"]
        == 1.0
    )
    assert result["fully_correct"] is (mutation is None)


def test_shared_input_oracle_retains_contract_and_parallel_path_evidence(
    tmp_path: Path,
) -> None:
    public, secret = tmp_path / "public.json", tmp_path / "secret.json"
    generate(
        tmp_path / "repos", public, secret, sizes=[5], shapes=["diamond"], contracts=1
    )
    tasks = json.loads(secret.read_text())["tasks"]
    shared = next(row for row in tasks if row["id"].endswith("-shared"))
    expected = {
        ("npm:@scale/p0001", "npm:@scale/p0000", "diamond-left"),
        ("npm:@scale/p0002", "npm:@scale/p0000", "diamond-right"),
        ("npm:@scale/p0003", "npm:@scale/p0001", "diamond-join"),
        ("npm:@scale/p0003", "npm:@scale/p0002", "diamond-join"),
        ("npm:@scale/p0004", "npm:@scale/p0003", "diamond-left"),
        *(
            (
                f"npm:@scale/p{index:04d}",
                "shared-input:contracts/contract-0.yaml",
                "contract",
            )
            for index in (0, 1, 4)
        ),
    }
    assert {tuple(row) for row in shared["edges"]} == expected
