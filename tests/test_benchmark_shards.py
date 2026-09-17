from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest

from scripts.benchmark_shards_lib import (
    create_manifest,
    deterministic_shards,
    load_manifest,
    merge_shards,
    pending_shards,
    run_next,
    write_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _worker(path: Path) -> Path:
    path.write_text(
        "import json,sys\n"
        "start,end,out=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]\n"
        "json.dump([{'id': f'Q{i:03d}', 'value': i} for i in range(start,end)], open(out,'w'))\n"
    )
    return path


def test_deterministic_shards_are_bounded() -> None:
    shards = deterministic_shards(47, 20)
    assert [(s.start, s.end) for s in shards] == [(0, 20), (20, 40), (40, 47)]


def test_resume_executes_one_atomic_shard_at_a_time(tmp_path: Path) -> None:
    worker = _worker(tmp_path / "worker.py")
    out = tmp_path / "run"
    manifest = create_manifest(
        total=5,
        shard_size=2,
        command=[sys.executable, str(worker), "{start}", "{end}", "{output}"],
    )
    write_manifest(out, manifest)
    first = run_next(out)
    assert first is not None and (first.start, first.end) == (0, 2)
    assert len(pending_shards(out, load_manifest(out))) == 2
    second = run_next(out)
    assert second is not None and (second.start, second.end) == (2, 4)
    third = run_next(out)
    assert third is not None and (third.start, third.end) == (4, 5)
    assert run_next(out) is None
    rows = json.loads(merge_shards(out).read_text())
    assert [row["id"] for row in rows] == ["Q000", "Q001", "Q002", "Q003", "Q004"]


def test_incomplete_shard_is_never_sealed(tmp_path: Path) -> None:
    worker = tmp_path / "bad.py"
    worker.write_text(
        "import json,sys\njson.dump([{'id':'only-one'}], open(sys.argv[3],'w'))\n"
    )
    out = tmp_path / "run"
    write_manifest(
        out,
        create_manifest(
            total=3,
            shard_size=3,
            command=[sys.executable, str(worker), "{start}", "{end}", "{output}"],
        ),
    )
    with pytest.raises(ValueError, match="row count mismatch"):
        run_next(out)
    assert len(pending_shards(out, load_manifest(out))) == 1
    assert not (out / "shards" / "00000-00002.json").exists()


def test_merge_rejects_partial_coverage(tmp_path: Path) -> None:
    worker = _worker(tmp_path / "worker.py")
    out = tmp_path / "run"
    write_manifest(
        out,
        create_manifest(
            total=4,
            shard_size=2,
            command=[sys.executable, str(worker), "{start}", "{end}", "{output}"],
        ),
    )
    run_next(out)
    with pytest.raises(ValueError, match="cannot merge incomplete benchmark"):
        merge_shards(out)


def test_manifest_is_immutable(tmp_path: Path) -> None:
    out = tmp_path / "run"
    first = create_manifest(
        total=4, shard_size=2, command=["worker", "{start}", "{end}", "{output}"]
    )
    write_manifest(out, first)
    second = create_manifest(
        total=4, shard_size=1, command=["worker", "{start}", "{end}", "{output}"]
    )
    with pytest.raises(ValueError, match="manifest differs"):
        write_manifest(out, second)


def test_warmup_is_explicit_and_required(tmp_path: Path) -> None:
    from scripts.benchmark_shards_lib import run_warmup, warmup_complete

    worker = _worker(tmp_path / "worker.py")
    warm = tmp_path / "warm.py"
    marker = tmp_path / "did-warm"
    warm.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ok')\n"
    )
    out = tmp_path / "run"
    write_manifest(
        out,
        create_manifest(
            total=2,
            shard_size=1,
            command=[sys.executable, str(worker), "{start}", "{end}", "{output}"],
            warmup_command=[sys.executable, str(warm)],
        ),
    )
    assert not warmup_complete(out, load_manifest(out))
    with pytest.raises(ValueError, match="warmup is incomplete"):
        run_next(out)
    assert run_warmup(out)
    assert marker.read_text() == "ok"
    assert warmup_complete(out, load_manifest(out))
    assert not run_warmup(out)
    assert run_next(out) is not None


def test_manifest_identity_binds_sealed_shards(tmp_path: Path) -> None:
    from scripts.benchmark_shards_lib import manifest_identity

    worker = _worker(tmp_path / "worker.py")
    out = tmp_path / "run"
    manifest = create_manifest(
        total=2,
        shard_size=2,
        command=[sys.executable, str(worker), "{start}", "{end}", "{output}"],
        run_identity="sha256:candidate-a",
    )
    write_manifest(out, manifest)
    run_next(out)
    seal = json.loads((out / "shards" / "00000-00001.seal.json").read_text())
    assert seal["manifest_identity"] == manifest_identity(manifest)
    assert manifest["run_identity"] == "sha256:candidate-a"
