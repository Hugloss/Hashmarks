"""Source-local correspondence for externally produced diagnostic revision claims.

The producer supplies the claimed revision. The caller separately supplies
canonical source-observation packets. This pure projection does not run LSP,
read the filesystem, create an index, or independently authenticate packets.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

_FILE_REVISION = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MEMBERS = 32
EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA = "hashmarks.external-diagnostic-observation.v1"


def diagnostic_identity(row: Mapping[str, object]) -> str:
    """Preserve the existing diagnostic fact identity, excluding provenance."""
    facts = {
        key: row.get(key)
        for key in ("tool", "rule", "path", "symbol", "line", "column", "message")
        if row.get(key) is not None
    }
    raw = json.dumps(
        facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def normalize_source_revision_claims(
    claims: Mapping[str, str] | None, scope_paths: Sequence[str]
) -> dict[str, str] | None:
    """Validate explicit producer claims without inventing missing revisions."""
    if claims is None:
        return None
    if not isinstance(claims, Mapping) or len(claims) > _MAX_MEMBERS:
        raise ValueError("source_revisions must be a mapping of at most 32 members")
    scope = {normalize_relative_path(path, allow_root=False) for path in scope_paths}
    normalized: dict[str, str] = {}
    for raw_path, revision in claims.items():
        if not isinstance(raw_path, str):
            raise ValueError("source_revisions paths must be strings")
        path = normalize_relative_path(raw_path, allow_root=False)
        if path not in scope:
            raise ValueError("source_revisions must be within declared scope_paths")
        if path in normalized:
            raise ValueError("source_revisions contain duplicate normalized paths")
        if not isinstance(revision, str) or not _FILE_REVISION.fullmatch(revision):
            raise ValueError("source_revisions values must be 64 lowercase hex digits")
        normalized[path] = revision
    return dict(sorted(normalized.items()))


def _source_member_qualified(
    source: Mapping[str, object], member: Mapping[str, object], path: str
) -> bool:
    revision = member.get("member_revision")
    return isinstance(revision, str) and all(
        (
            member.get("path") == path,
            member.get("state") == "known-present",
            source.get("availability") == "observed",
            source.get("completeness") == "complete",
            bool(source.get("observation_identity")),
            bool(_FILE_REVISION.fullmatch(revision)),
        )
    )


def _indexed_source_packets(
    source_observations: Sequence[Mapping[str, object]],
    claims: Mapping[str, str],
) -> tuple[dict[str, list[Mapping[str, object]]], int]:
    endpoints: dict[str, list[Mapping[str, object]]] = {}
    unused = 0
    for source in source_observations:
        if not isinstance(source, Mapping):
            raise ValueError("source_observations must contain mappings")
        member = source.get("member")
        path = member.get("path") if isinstance(member, Mapping) else None
        if not isinstance(path, str) or path not in claims:
            unused += 1
            continue
        endpoints.setdefault(path, []).append(source)
    return endpoints, unused


def _member_comparison(
    path: str,
    claimed: str,
    endpoints: Sequence[Mapping[str, object]],
    diagnostic_generation: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path,
        "producer_claimed_member_revision": claimed,
        "observed_member_revision": None,
        "source_observation_identity": None,
        "source_generation": None,
        "source_freshness": "unknown",
        "generation_relation": "unknown",
    }
    if len(endpoints) != 1:
        state = "unknown"
        reason = (
            "source-observation-missing"
            if not endpoints
            else "ambiguous-source-observations"
        )
    else:
        source = endpoints[0]
        member = source.get("member")
        member = member if isinstance(member, Mapping) else {}
        row["source_observation_identity"] = source.get("observation_identity")
        row["source_generation"] = source.get("generation")
        row["source_freshness"] = source.get("freshness", "unknown")
        row["observed_member_revision"] = member.get("member_revision")
        row["generation_relation"] = (
            "same" if source.get("generation") == diagnostic_generation else "different"
        )
        if source.get("schema") != operation_schema("source_observation", "member"):
            state, reason = "unknown", "unsupported-source-observation-schema"
        elif not _source_member_qualified(source, member, path):
            state, reason = "unknown", "source-member-not-revision-qualified"
        elif source.get("freshness") != "current":
            state, reason = "unknown", "source-observation-freshness-unproven"
        elif claimed != member["member_revision"]:
            state, reason = "different", "claimed-and-observed-member-revisions-differ"
        else:
            state, reason = (
                "matching",
                "producer-claim-matches-observed-member-revision",
            )
    return {
        **row,
        "state": state,
        "reason": reason,
        "claim_authority": "producer-claimed",
        "comparison_authority": "source-local-caller-supplied-observations",
    }


def diagnostic_source_revision_evidence(
    diagnostic: Mapping[str, object],
    source_observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compare claimed source revisions with explicitly retained member evidence.

    A match means only that producer-claimed revision bytes equal one fresh,
    caller-supplied source observation. It cannot prove an LSP executed against
    those bytes, or that verification is valid for the repository as a whole.
    """
    if diagnostic.get("schema") != EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA:
        raise ValueError("unsupported diagnostic observation schema")
    if len(source_observations) > _MAX_MEMBERS:
        raise ValueError("source_observations exceeds 32 members")
    claims = diagnostic.get("source_revisions")
    if claims is None:
        claims = {}
    if not isinstance(claims, Mapping):
        raise ValueError("diagnostic source_revisions must be a mapping")
    scoped = normalize_source_revision_claims(claims, diagnostic.get("scope_paths", ()))
    claims_by_path = scoped or {}
    endpoints, unused = _indexed_source_packets(source_observations, claims_by_path)
    rows = [
        _member_comparison(
            path, claimed, endpoints.get(path, []), diagnostic.get("codemap_generation")
        )
        for path, claimed in claims_by_path.items()
    ]
    diagnostics = diagnostic.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("diagnostics must be a list")
    unbound = sum(
        1
        for row in diagnostics
        if not isinstance(row, Mapping) or row.get("path") not in claims_by_path
    )
    return {
        "schema": "hashmarks.diagnostic-source-revision-evidence.v1",
        "repository_identity": diagnostic.get("repository_identity"),
        "diagnostic_generation": diagnostic.get("codemap_generation"),
        "producer": diagnostic.get("producer"),
        "collection": diagnostic.get("collection"),
        "diagnostic_outcome": diagnostic.get("outcome"),
        "rows": rows,
        "matching_count": sum(row["state"] == "matching" for row in rows),
        "different_count": sum(row["state"] == "different" for row in rows),
        "unknown_count": sum(row["state"] == "unknown" for row in rows),
        "unclaimed_diagnostic_count": unbound,
        "ignored_source_observation_count": unused,
        "coverage": (
            "unknown"
            if not claims_by_path
            else "complete-for-declared-members"
            if all(row["state"] != "unknown" for row in rows)
            else "incomplete"
        ),
        "authority": "descriptive-source-revision-correspondence-only",
        "execution_effect": "none",
    }
