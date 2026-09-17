from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .producer_identity import native_producer_implementation_identity
from .test_shards import repository_content_identity

QUALIFIED_IMPORT_SCHEMA = "hashmarks.qualified-import-identity.v1"
QUALIFIED_SHARED_INPUT_SCHEMA = "hashmarks.qualified-shared-input-identity.v1"


def _codemap_repository_identity(codemap: Any) -> str:
    excluded = [codemap.state_dir]
    artifact_path = getattr(getattr(codemap, "artifacts", None), "db_path", None)
    if isinstance(artifact_path, Path):
        excluded.append(artifact_path)
    return repository_content_identity(codemap.workspace, excluded_paths=tuple(excluded))


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity(domain: str, value: Mapping[str, object]) -> str:
    digest = hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical_bytes(value))
    return "sha256:" + digest.hexdigest()


def qualified_import_identity(codemap: Any, *, source_path: str, target: str) -> dict[str, object]:
    """Project exact import-owner identity from existing Hashmarks resolver evidence."""
    # Qualified identity is stronger than a best-effort query: every path that
    # contributes ownership authority must be reconciled against current bytes
    # before an identity can be issued. This is especially important without a
    # live watcher, where a deleted leaf can otherwise remain in the durable map.
    codemap._ensure_map_ready()
    codemap._ensure_path_current(source_path)
    owners, ambiguous = codemap._resolve_import_owner_evidence(source_path, target)
    for owner in tuple(owners):
        codemap._ensure_path_current(str(owner))
    owners, ambiguous = codemap._resolve_import_owner_evidence(source_path, target)
    owner_paths = sorted(dict.fromkeys(str(path) for path in owners))
    symbol = target.lstrip(".").rsplit(".", 1)[-1]
    status = "ambiguous" if ambiguous else "resolved" if owner_paths else "unresolved"
    payload: dict[str, object] = {
        "schema": QUALIFIED_IMPORT_SCHEMA,
        "repository_identity": _codemap_repository_identity(codemap),
        "producer_implementation_identity": native_producer_implementation_identity(),
        "symbol": symbol,
        "owner_paths": owner_paths,
    }
    return {
        **payload,
        "source_path": source_path,
        "requested_target": target,
        "status": status,
        "ambiguous": bool(ambiguous),
        "qualified_identity": _identity(QUALIFIED_IMPORT_SCHEMA, payload) if status == "resolved" else None,
        "authority": "repository-intelligence-only",
    }


def _is_declared_shared_edge(row: Mapping[str, object], synthetic: str) -> bool:
    return (
        str(row.get("producer") or "") == "declared-project-links"
        and str(row.get("target") or "") == synthetic
    )


def _shared_input_projects(codemap: Any, synthetic: str) -> list[dict[str, str]]:
    rows = [row for row in codemap.store.project_edges() if _is_declared_shared_edge(row, synthetic)]
    rows.sort(key=lambda row: (str(row.get("source") or ""), str(row.get("kind") or "")))
    return [
        {"project_id": str(row.get("source") or ""), "kind": str(row.get("kind") or "")}
        for row in rows
    ]


def _shared_input_node_matches(row: Mapping[str, object], rel: str) -> bool:
    metadata = row.get("metadata")
    metadata_path = metadata.get("path") if isinstance(metadata, Mapping) else None
    return (
        str(row.get("producer") or "") == "declared-project-links"
        and str(row.get("kind") or "") == "shared-input"
        and str(metadata_path or row.get("root") or "") == rel
    )


def _shared_input_status(node: object, fresh: bool) -> str:
    if node is None:
        return "unresolved"
    return "resolved" if fresh else "stale"


def _shared_input_payload(codemap: Any, rel: str, projects: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema": QUALIFIED_SHARED_INPUT_SCHEMA,
        "repository_identity": _codemap_repository_identity(codemap),
        "producer_implementation_identity": native_producer_implementation_identity(),
        "path": rel,
        "content_sha256": codemap._manifest_digest(rel),
        "projects": projects,
    }


def qualified_shared_input_identity(codemap: Any, *, relpath: str) -> dict[str, object]:
    """Bind declared cross-repository shared-input provenance without execution semantics."""
    from .paths import normalize_relative_path

    rel = normalize_relative_path(relpath, allow_root=False)
    synthetic = f"shared-input:{rel}"
    node = next((row for row in codemap.store.project_nodes() if _shared_input_node_matches(row, rel)), None)
    projects = _shared_input_projects(codemap, synthetic) if node is not None else []
    fresh, stale_reason = codemap._evidence_fresh("project", "declared-project-links")
    status = _shared_input_status(node, fresh)
    payload = _shared_input_payload(codemap, rel, projects)
    identity_available = status == "resolved" and payload["content_sha256"] is not None and bool(projects)
    return {
        **payload,
        "status": status,
        "fresh": bool(fresh),
        "stale_reason": stale_reason,
        "qualified_identity": _identity(QUALIFIED_SHARED_INPUT_SCHEMA, payload) if identity_available else None,
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
    }
