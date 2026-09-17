from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "hashmarks.benchmark-shards.v1"


@dataclass(frozen=True, slots=True)
class Shard:
    index: int
    start: int
    end: int

    @property
    def count(self) -> int:
        return self.end - self.start

    @property
    def key(self) -> str:
        return f"{self.start:05d}-{self.end - 1:05d}"


def deterministic_shards(total: int, shard_size: int) -> tuple[Shard, ...]:
    if total < 0:
        raise ValueError("total must be >= 0")
    if shard_size <= 0:
        raise ValueError("shard_size must be > 0")
    return tuple(
        Shard(index=i, start=start, end=min(total, start + shard_size))
        for i, start in enumerate(range(0, total, shard_size))
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_identity(manifest: dict[str, Any]) -> str:
    return "sha256:" + _sha256_bytes(_canonical_json_bytes(manifest))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def create_manifest(*, total: int, shard_size: int, command: Sequence[str], id_field: str = "id", warmup_command: Sequence[str] | None = None, run_identity: str = "unbound") -> dict[str, Any]:
    shards = deterministic_shards(total, shard_size)
    return {
        "schema": SCHEMA,
        "total": total,
        "shard_size": shard_size,
        "id_field": id_field,
        "run_identity": run_identity,
        "command": list(command),
        "warmup_command": list(warmup_command or ()),
        "shards": [
            {"index": s.index, "start": s.start, "end": s.end, "key": s.key}
            for s in shards
        ],
    }


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    path = output_dir / "manifest.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != manifest:
            raise ValueError("existing benchmark shard manifest differs from requested plan")
        return path
    _atomic_write(path, _canonical_json_bytes(manifest))
    return path


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "manifest.json"
    value = json.loads(path.read_text())
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported benchmark shard manifest schema")
    return value




def warmup_marker_path(output_dir: Path) -> Path:
    return output_dir / "warmup.seal.json"


def warmup_complete(output_dir: Path, manifest: dict[str, Any]) -> bool:
    command = manifest.get("warmup_command") or []
    if not command:
        return True
    path = warmup_marker_path(output_dir)
    if not path.exists():
        return False
    try:
        marker = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        marker.get("schema") == SCHEMA
        and marker.get("command") == command
        and marker.get("manifest_identity") == manifest_identity(manifest)
        and marker.get("complete") is True
    )


def run_warmup(output_dir: Path, *, timeout_seconds: float | None = None) -> bool:
    manifest = load_manifest(output_dir)
    command = manifest.get("warmup_command") or []
    if not command:
        return False
    if warmup_complete(output_dir, manifest):
        return False
    subprocess.run(list(command), check=True, timeout=timeout_seconds)
    _atomic_write(
        warmup_marker_path(output_dir),
        _canonical_json_bytes({"schema": SCHEMA, "command": command, "manifest_identity": manifest_identity(manifest), "complete": True}),
    )
    return True

def shard_path(output_dir: Path, shard: Shard) -> Path:
    return output_dir / "shards" / f"{shard.key}.json"


def seal_path(output_dir: Path, shard: Shard) -> Path:
    return output_dir / "shards" / f"{shard.key}.seal.json"


def _read_rows(path: Path, *, expected_count: int, id_field: str) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"shard output must be a JSON list: {path}")
    if len(rows) != expected_count:
        raise ValueError(f"shard row count mismatch: expected {expected_count}, got {len(rows)}")
    ids: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every shard row must be a JSON object")
        if id_field not in row:
            raise ValueError(f"missing id field {id_field!r}")
        ids.append(row[id_field])
    if len(set(map(str, ids))) != len(ids):
        raise ValueError("duplicate ids inside shard")
    return rows


def _marker_matches_shard(
    marker: dict[str, Any],
    *,
    manifest_id: str,
    shard: Shard,
    row_count: int,
    data_sha256: str,
) -> bool:
    expected = {
        "schema": SCHEMA,
        "manifest_identity": manifest_id,
        "start": shard.start,
        "end": shard.end,
        "row_count": row_count,
        "sha256": data_sha256,
    }
    return all(marker.get(key) == value for key, value in expected.items())


def verify_sealed_shard(output_dir: Path, shard: Shard, *, id_field: str) -> bool:
    data_path = shard_path(output_dir, shard)
    marker_path = seal_path(output_dir, shard)
    if not data_path.exists() or not marker_path.exists():
        return False
    try:
        rows = _read_rows(data_path, expected_count=shard.count, id_field=id_field)
        marker = json.loads(marker_path.read_text())
        data = data_path.read_bytes()
        manifest_id = manifest_identity(load_manifest(output_dir))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return _marker_matches_shard(
        marker,
        manifest_id=manifest_id,
        shard=shard,
        row_count=len(rows),
        data_sha256=_sha256_bytes(data),
    )


def pending_shards(output_dir: Path, manifest: dict[str, Any]) -> tuple[Shard, ...]:
    id_field = str(manifest.get("id_field", "id"))
    planned = tuple(Shard(int(s["index"]), int(s["start"]), int(s["end"])) for s in manifest["shards"])
    return tuple(s for s in planned if not verify_sealed_shard(output_dir, s, id_field=id_field))


def _render_command(template: Sequence[str], shard: Shard, output: Path) -> list[str]:
    replacements = {
        "{start}": str(shard.start),
        "{end}": str(shard.end),
        "{output}": str(output),
        "{index}": str(shard.index),
    }
    rendered: list[str] = []
    for arg in template:
        value = arg
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        rendered.append(value)
    return rendered


def execute_shard(
    output_dir: Path,
    manifest: dict[str, Any],
    shard: Shard,
    *,
    timeout_seconds: float | None = None,
) -> Path:
    id_field = str(manifest.get("id_field", "id"))
    final_path = shard_path(output_dir, shard)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"hashmarks-shard-{shard.key}-", dir=output_dir) as tmp:
        candidate = Path(tmp) / "candidate.json"
        command = _render_command(manifest["command"], shard, candidate)
        subprocess.run(command, check=True, timeout=timeout_seconds)
        rows = _read_rows(candidate, expected_count=shard.count, id_field=id_field)
        data = _canonical_json_bytes(rows)
        _atomic_write(final_path, data)
        marker = {
            "schema": SCHEMA,
            "manifest_identity": manifest_identity(manifest),
            "index": shard.index,
            "start": shard.start,
            "end": shard.end,
            "row_count": len(rows),
            "sha256": _sha256_bytes(data),
        }
        _atomic_write(seal_path(output_dir, shard), _canonical_json_bytes(marker))
    return final_path


def run_next(output_dir: Path, *, timeout_seconds: float | None = None) -> Shard | None:
    manifest = load_manifest(output_dir)
    if not warmup_complete(output_dir, manifest):
        raise ValueError("benchmark warmup is incomplete; run the warm command first")
    pending = pending_shards(output_dir, manifest)
    if not pending:
        return None
    shard = pending[0]
    execute_shard(output_dir, manifest, shard, timeout_seconds=timeout_seconds)
    return shard


def _merged_rows(output_dir: Path, planned: tuple[Shard, ...], id_field: str) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for shard in planned:
        rows = _read_rows(shard_path(output_dir, shard), expected_count=shard.count, id_field=id_field)
        for row in rows:
            key = str(row[id_field])
            if key in seen:
                raise ValueError(f"duplicate id across shards: {key}")
            seen.add(key)
            all_rows.append(row)
    return all_rows


def merge_shards(output_dir: Path, *, aggregate_name: str = "aggregate.json") -> Path:
    manifest = load_manifest(output_dir)
    id_field = str(manifest.get("id_field", "id"))
    planned = tuple(Shard(int(item["index"]), int(item["start"]), int(item["end"])) for item in manifest["shards"])
    missing = [shard.key for shard in planned if not verify_sealed_shard(output_dir, shard, id_field=id_field)]
    if missing:
        raise ValueError(f"cannot merge incomplete benchmark; missing/invalid shards: {', '.join(missing)}")
    all_rows = _merged_rows(output_dir, planned, id_field)
    if len(all_rows) != int(manifest["total"]):
        raise ValueError(f"aggregate count mismatch: expected {manifest['total']}, got {len(all_rows)}")
    path = output_dir / aggregate_name
    _atomic_write(path, _canonical_json_bytes(all_rows))
    return path
