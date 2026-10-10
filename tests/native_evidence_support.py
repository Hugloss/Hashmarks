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
TASK = "Change normalize_widget in src/engine.py to lowercase the trimmed value and verify its semantics."


def materialize_scip(root: Path, source: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "src", root / "src", dirs_exist_ok=True)
    for name in (
        "pyproject.toml",
        "pyrightconfig.json",
        "environment.json",
        "package.json",
        "tsconfig.json",
    ):
        if (source / name).exists():
            shutil.copyfile(source / name, root / name)


def import_native_scip(cm: Any, source: Path) -> None:
    cm.import_scip(
        source / "index.json",
        provenance=json.loads((source / "provenance.json").read_text()),
    )


def materialize_dependency(root: Path, source: Path) -> list[str]:
    """Replace admitted inputs; captures remain outside the observed repository."""
    for name in ("vendor", "pyproject.toml", "uv.lock", "pom.xml"):
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for path in sorted(source.rglob("*")):
        if path.name not in {"pyproject.toml", "uv.lock", "pom.xml"}:
            continue
        relative = path.relative_to(source)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        paths.append(relative.as_posix())
    return paths


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
