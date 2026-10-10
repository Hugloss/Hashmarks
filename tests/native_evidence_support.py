"""Real-file corpus materialization and observable evidence assertions for tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from hashmarks.adapters import (
    maven_dependency_observation,
    uv_lock_dependency_observation,
)
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_presentation import FORMATS, presentation_response

CORPUS = Path(__file__).parent / "fixtures" / "dependency_dogfood"
SCIP_CORPUS = Path(__file__).parent / "fixtures" / "native_scip"
LSP_CORPUS = Path(__file__).parent / "fixtures" / "native_lsp"
TASK = "Change normalize_widget in src/engine.py to lowercase the trimmed value and verify its semantics."


def _replace_inputs(root: Path, source: Path, paths: list[str]) -> list[str]:
    """Replace exactly the previous fixture's files, preserving unrelated inputs."""
    ownership = root.parent / (root.name + ".fixture-inputs.json")
    if ownership.exists():
        for name in json.loads(ownership.read_text()):
            (root / name).unlink(missing_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    for name in paths:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    ownership.write_text(json.dumps(paths))
    return paths


def materialize_scip(root: Path, source: Path) -> None:
    paths = [
        path.relative_to(source).as_posix()
        for path in sorted((source / "src").rglob("*"))
        if path.is_file() and path.suffix in (".py", ".ts")
    ]
    for name in (
        "pyproject.toml",
        "pyrightconfig.json",
        "environment.json",
        "package.json",
        "tsconfig.json",
    ):
        if (source / name).exists():
            paths.append(name)
    _replace_inputs(root, source, paths)


def lsp_capture(root: Path, source: Path, name: str) -> dict[str, Any]:
    """Rebase only fixture-owned file URIs; raw capture bytes remain untouched."""
    metadata = json.loads((source / "capture.json").read_text())
    original = metadata["original_root_uri"]
    owned = {
        original + "/" + path: (root / path).as_uri()
        for path in metadata["source_revisions"]
    }

    def rebase(value: Any) -> Any:
        if isinstance(value, str):
            return owned.get(value, value)
        if isinstance(value, list):
            return [rebase(item) for item in value]
        if isinstance(value, dict):
            return {key: rebase(item) for key, item in value.items()}
        return value

    row = next(
        row
        for row in json.loads((source / "captures.json").read_text())
        if row["name"] == name
    )
    return rebase(row["capture"])


def import_native_scip(cm: Any, source: Path) -> None:
    cm.import_scip(
        source / "index.json",
        provenance=json.loads((source / "provenance.json").read_text()),
    )


def materialize_dependency(root: Path, source: Path) -> list[str]:
    """Replace admitted inputs; captures remain outside the observed repository."""
    paths = [
        path.relative_to(source).as_posix()
        for path in sorted(source.rglob("*"))
        if path.name in {"pyproject.toml", "uv.lock", "pom.xml"}
    ]
    return _replace_inputs(root, source, paths)


def input_revisions(root: Path, paths: list[str]) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "member_revision": hash_bytes(
                (root / path).read_bytes(), domain=FILE_DOMAIN
            ).hash,
        }
        for path in paths
    ]


def dependency_capture(
    producer: str, source: Path, inputs: list[dict[str, str]]
) -> Any:
    if producer == "uv":
        return uv_lock_dependency_observation(
            lock=(source / "uv.lock").read_bytes(), repository_inputs=inputs
        )
    return maven_dependency_observation(
        trees={"compile": (source / "tree.json").read_bytes()},
        inventories={"compile": (source / "list.txt").read_bytes()},
        complete_tree_contexts=("compile",),
        complete_inventory_contexts=("compile",),
        repository_inputs=inputs,
    )


def assert_projection(native: Any, operation: str, mode: str = "default") -> None:
    """Check exact selected evidence and explicit exclusions across all encodings."""
    for format in FORMATS:
        response: Any = presentation_response(
            operation, native, format=format, result_mode=mode
        )
        if format == "none":
            assert response == native
            continue
        assert response["result"] == native
        projected = response["presentation"]
        assert projected["coverage"] == "projection-only"
        for group in projected["groups"]:
            assert (
                group["count_observed_in_packet"]
                == len(group["findings"]) + group["omitted_from_presentation"]
            )
            for row in group["findings"]:
                assert len(row["source_refs"]) == 1
                value = native
                for part in row["source_refs"][0].split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(key)] if isinstance(value, list) else value[key]
                assert row["details"] == value


def semantic_dependency_fields(observation: Any) -> Any:
    return {
        key: observation[key]
        for key in (
            "definition_identity",
            "resolution_identity",
            "components",
            "selections",
            "inventory",
            "relationships",
            "coverage",
            "repository_inputs",
        )
    }
