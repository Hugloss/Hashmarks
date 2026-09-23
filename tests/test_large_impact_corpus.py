import json
from pathlib import Path

import pytest

from scripts.generate_large_impact_corpus import generate


@pytest.mark.parametrize("kind", ["python", "typescript", "go", "polyglot"])
def test_large_impact_corpus_keeps_answers_external_and_materializes_targets(
    tmp_path: Path, kind: str
) -> None:
    repo = tmp_path / "repo"
    public_path = tmp_path / "public.json"
    secret_path = tmp_path / "secret.json"

    manifest = generate(
        repo,
        public_path,
        secret_path,
        kind=kind,
        noise_files=3,
        tasks=3,
    )

    public = json.loads(public_path.read_text(encoding="utf-8"))
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    assert manifest["answer_key_inside_worker_repo"] is False
    assert len(public["tasks"]) == len(secret["tasks"]) == 3
    assert set(public["tasks"][0]) == {"id", "query"}
    assert "expected_edit_path" not in json.dumps(public)
    for row in secret["tasks"]:
        assert (repo / row["expected_edit_path"]).is_file()
        assert (repo / row["expected_verify_path"]).is_file()
        assert (repo / row["expected_dependency_path"]).is_file()


def test_large_impact_corpus_rejects_invalid_shape_and_answer_key_location(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unsupported kind"):
        generate(
            tmp_path / "repo",
            tmp_path / "public.json",
            tmp_path / "secret.json",
            kind="ruby",
            noise_files=0,
            tasks=1,
        )
    repo = tmp_path / "inside"
    with pytest.raises(ValueError, match="outside"):
        generate(
            repo,
            repo / "public.json",
            tmp_path / "secret.json",
            kind="python",
            noise_files=0,
            tasks=1,
        )
