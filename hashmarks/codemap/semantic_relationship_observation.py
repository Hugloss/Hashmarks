"""Compose current SCIP and request-local supplied claims under CodeMap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from hashmarks.paths import normalize_relative_path
from hashmarks.producer_identity import native_producer_implementation_identity

from .lsp_relationship_adapter import lsp_relationship_observation
from .scip_relationship_adapter import scip_relationship_observations
from .semantic_relationship_model import content_identity, finish_observation
from .semantic_relationship_source import RelationshipSourceResolver

if TYPE_CHECKING:
    from .engine import CodeMap


def exact_relationship_target(codemap: CodeMap, target: str) -> dict[str, Any]:
    """Admit an explicit unique native definition only for producer-claim reads."""
    try:
        return codemap._exact_locality_target(target)
    except KeyError:
        path, name = target.split("::", 1)
        path = normalize_relative_path(
            path.strip().replace("\\", "/"), allow_root=False
        )
        rows = codemap.store.native_definitions_for_path(
            path, name=name.strip(), limit=129
        )
        if not rows:
            raise KeyError(
                f"native relationship subject is missing: {target}"
            ) from None
        resolver = RelationshipSourceResolver(codemap)
        if not resolver.admitted(path):
            raise PermissionError(
                f"native relationship subject is not admitted: {target}"
            ) from None
        if (
            len(rows) != 1
            or not codemap._evidence_fresh("scip", str(rows[0]["producer"]))[0]
        ):
            raise KeyError(
                f"native relationship subject is missing, ambiguous, bounded or stale: {target}"
            ) from None
        return {
            **rows[0],
            "path": path,
            "name": name.strip(),
            "qualname": name.strip(),
            "start_line": rows[0]["line"],
        }


def semantic_relationship_observation(
    codemap: CodeMap,
    target: Mapping[str, Any],
    captures: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    resolver = RelationshipSourceResolver(codemap)
    subject = f"{target['path']}::{target['qualname']}"
    observations = scip_relationship_observations(codemap, target, resolver)
    observations.extend(
        lsp_relationship_observation(capture, subject, resolver) for capture in captures
    )
    freshness = codemap._query_freshness_fields()
    stale = freshness.get("stale")
    repository = {
        "scope_identity": content_identity(str(codemap.workspace)),
        "content_identity": "sha256:" + codemap._workspace_fingerprint_from_store(),
        "generation": codemap.store.generation(),
        "freshness": "current"
        if stale is False
        else "stale"
        if stale is True
        else "unknown",
        "observer_identity": native_producer_implementation_identity(),
    }
    return finish_observation(subject, repository, observations)
