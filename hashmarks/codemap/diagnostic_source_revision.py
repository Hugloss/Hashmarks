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
from copy import deepcopy

from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .diagnostic_provenance import _revision_scope, diagnostic_member_claims

_FILE_REVISION = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MEMBERS = 32
EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA = "hashmarks.external-diagnostic-observation.v1"
DIAGNOSTIC_SOURCE_REVISION_EVIDENCE_SCHEMA = (
    "hashmarks.diagnostic-source-revision-evidence.v1"
)


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
    claims: object, scope_paths: object
) -> dict[str, str] | None:
    """Validate explicit producer claims without inventing missing revisions."""
    if claims is None:
        return None
    if not isinstance(claims, Mapping) or len(claims) > _MAX_MEMBERS:
        raise ValueError("source_revisions must be a mapping of at most 32 members")
    scope = _revision_scope(scope_paths)
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


def diagnostic_revision_delta(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Keep producer revision changes separate from diagnostic fact identity."""
    prior = normalize_source_revision_claims(
        before.get("source_revisions"), before.get("scope_paths", ())
    )
    later = normalize_source_revision_claims(
        after.get("source_revisions"), after.get("scope_paths", ())
    )
    return {
        "before": prior,
        "after": later,
        "changed": prior != later,
        "claim_authority": "producer-claimed",
    }


def diagnostic_revision_claim_reason(
    diagnostic: Mapping[str, object], member: Mapping[str, object]
) -> str | None:
    """A producer's contradictory revision cannot support source correspondence."""
    try:
        claims = normalize_source_revision_claims(
            diagnostic.get("source_revisions"), diagnostic.get("scope_paths", ())
        )
    except (TypeError, ValueError):
        return "invalid-diagnostic-source-revisions"
    path = member.get("path")
    claimed = (claims or {}).get(path) if isinstance(path, str) else None
    if claimed is not None and claimed != member.get("member_revision"):
        return "diagnostic-source-revision-mismatch"
    return None


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
        elif source.get("freshness") not in ("current", "unknown"):
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


def _revision_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Account for every declared member without upgrading repository freshness."""
    return {
        "matching_count": sum(row["state"] == "matching" for row in rows),
        "different_count": sum(row["state"] == "different" for row in rows),
        "unknown_count": sum(row["state"] == "unknown" for row in rows),
        "coverage": (
            "unknown"
            if not rows
            else "complete-for-declared-members"
            if all(row["state"] != "unknown" for row in rows)
            else "incomplete"
        ),
    }


def diagnostic_source_revision_evidence(
    diagnostic: Mapping[str, object],
    source_observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compare claimed source revisions with explicitly retained member evidence.

    A match means only that producer-claimed revision bytes equal one stable,
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
    provenance = diagnostic_member_claims(diagnostic).get("source_provenance")
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
        "schema": DIAGNOSTIC_SOURCE_REVISION_EVIDENCE_SCHEMA,
        "repository_identity": diagnostic.get("repository_identity"),
        "diagnostic_generation": diagnostic.get("codemap_generation"),
        "producer": diagnostic.get("producer"),
        **(
            {
                "source_provenance": provenance,
                "scope_paths": sorted(
                    _revision_scope(diagnostic.get("scope_paths", ()))
                ),
            }
            if provenance is not None
            else {}
        ),
        "collection": diagnostic.get("collection"),
        "diagnostic_outcome": diagnostic.get("outcome"),
        "rows": rows,
        **_revision_summary(rows),
        "unclaimed_diagnostic_count": unbound,
        "ignored_source_observation_count": unused,
        "authority": "descriptive-source-revision-correspondence-only",
        "execution_effect": "none",
    }


def _validate_compared_revision_row(row: Mapping[str, object], generation: int) -> None:
    observed = row.get("observed_member_revision")
    identity = row.get("source_observation_identity")
    source_generation = row.get("source_generation")
    required = (
        isinstance(observed, str) and bool(_FILE_REVISION.fullmatch(observed)),
        isinstance(identity, str)
        and identity.startswith("sha256:")
        and bool(_FILE_REVISION.fullmatch(identity[7:])),
        type(source_generation) is int and source_generation >= 0,
        row.get("source_freshness") in ("current", "unknown"),
        row.get("generation_relation")
        == ("same" if source_generation == generation else "different"),
    )
    if not all(required):
        raise ValueError("compared source member is not revision-qualified")
    matching = row["producer_claimed_member_revision"] == observed
    if row["state"] != ("matching" if matching else "different"):
        raise ValueError("source revision comparison contradicts member revisions")


def _validate_revision_row(row: Mapping[str, object], generation: int) -> None:
    path = row.get("path")
    claimed = row.get("producer_claimed_member_revision")
    if (
        not isinstance(path, str)
        or normalize_relative_path(path, allow_root=False) != path
    ):
        raise ValueError("revision comparison paths must be canonical")
    if not isinstance(claimed, str) or not _FILE_REVISION.fullmatch(claimed):
        raise ValueError("invalid producer revision claim")
    if row.get("state") not in ("matching", "different", "unknown"):
        raise ValueError("invalid revision comparison state")
    if (
        row.get("claim_authority") != "producer-claimed"
        or row.get("comparison_authority")
        != "source-local-caller-supplied-observations"
    ):
        raise ValueError("invalid revision comparison authority")
    if row["state"] != "unknown":
        _validate_compared_revision_row(row, generation)


def _validated_revision_rows(
    rows: object, generation: int
) -> Sequence[Mapping[str, object]]:
    """Admit one bounded, unambiguous row per producer-claimed member."""
    if not isinstance(rows, list) or len(rows) > _MAX_MEMBERS:
        raise ValueError("revision rows must be a list of at most 32 members")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("revision rows must contain mappings")
        _validate_revision_row(row, generation)
    if len({row["path"] for row in rows}) != len(rows):
        raise ValueError("duplicate revision comparison paths")
    return rows


def validated_diagnostic_source_revision_evidence(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate the comparison's own bounded semantics, never producer execution."""
    generation = payload.get("diagnostic_generation")
    if type(generation) is not int or generation < 0:
        raise ValueError("invalid diagnostic generation")
    rows = _validated_revision_rows(payload.get("rows"), generation)
    summary = _revision_summary(rows)
    _validate_revision_summary(payload, summary)
    member_claims = diagnostic_member_claims(
        {
            "scope_paths": payload.get("scope_paths", ()),
            "source_revisions": {
                row["path"]: row["producer_claimed_member_revision"] for row in rows
            },
            **(
                {"source_provenance": payload["source_provenance"]}
                if "source_provenance" in payload
                else {}
            ),
        }
    )
    return {
        "source_revision_rows": deepcopy(rows),
        "source_revision_coverage": summary["coverage"],
        **member_claims,
    }


def _validate_revision_summary(
    payload: Mapping[str, object], summary: Mapping[str, object]
) -> None:
    """Counts preserve both compared and explicitly unclaimed evidence."""
    for field in (
        "matching_count",
        "different_count",
        "unknown_count",
        "unclaimed_diagnostic_count",
        "ignored_source_observation_count",
    ):
        count = payload.get(field)
        if type(count) is not int or count < 0:
            raise ValueError("revision evidence counts must be nonnegative integers")
        if field in summary and count != summary[field]:
            raise ValueError("revision comparison counts do not account for rows")
    if payload.get("coverage") != summary["coverage"]:
        raise ValueError("revision comparison coverage does not account for rows")
