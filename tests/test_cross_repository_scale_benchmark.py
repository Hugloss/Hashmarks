import json
from pathlib import Path

import pytest

from scripts.score_cross_repository_scale import generate, run


def test_scale_generator_separates_public_and_secret(tmp_path: Path):
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
):
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
    assert len(source["edges"]) == 4


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
