import json
from pathlib import Path

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
