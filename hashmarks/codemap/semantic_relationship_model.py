"""Bounded direct producer claims; this model owns no semantic graph."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .diagnostic_provenance import COLLECTION_STATES

OBSERVATION_SCHEMA = operation_schema("structural_locality", "relationships")
DELTA_SCHEMA = operation_schema("evidence_comparison", "relationships")
AUTHORITY = "external-producer-claims-only"
PACKET_MAX_BYTES = 524_288
CAPTURE_MAX_BYTES = 1_048_576
OBSERVATION_LIMIT = 32
CLAIM_LIMIT = 128
CANDIDATE_LIMIT = 64
COMPACT_CLAIM_LIMIT = 8
RELATIONSHIP_KINDS = frozenset(
    {"implementation", "type_definition", "definition", "reference", "call"}
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def content_identity(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def portable_copy(value: Any, *, maximum: int = CAPTURE_MAX_BYTES) -> Any:
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("relationship input must be portable JSON") from exc
    if len(raw) > maximum:
        raise ValueError(f"relationship input exceeds {maximum} bytes")
    return json.loads(raw)


def bounded_token(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError(f"{field_name} must be a nonempty bounded string")
    return value


def claim_identity(claim: Mapping[str, Any]) -> str:
    return content_identity(
        {
            "producer": claim["producer"],
            "kind": claim["kind"],
            "source": claim["source"]["key"],
            "target": claim["target"]["key"],
        }
    )


def direct_claim(
    producer: str,
    kind: str,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    basis: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "producer": producer,
        "kind": kind,
        "source": deepcopy(dict(source)),
        "target": deepcopy(dict(target)),
        "basis": deepcopy(dict(basis)),
        "authority": AUTHORITY,
        "negative_evidence_admissible": False,
    }
    return {**value, "identity": claim_identity(value)}


@dataclass
class ProducerRelationshipObservation:
    producer: str
    configuration_identity: str | None
    scope: dict[str, Any]
    capability: dict[str, Any]
    collection_state: str
    capture_identity: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    source_bindings: list[dict[str, Any]] = field(default_factory=list)
    accounting: dict[str, int] = field(default_factory=dict)
    freshness: str = "unknown"
    truncated: bool = False

    def packet(self) -> dict[str, Any]:
        value = {
            "producer": self.producer,
            "configuration_identity": self.configuration_identity,
            "scope": self.scope,
            "capability": self.capability,
            "collection_state": self.collection_state,
            "capture_identity": self.capture_identity,
            "claims": self.claims,
            "source_bindings": self.source_bindings,
            "accounting": {**self.accounting, "retained": len(self.claims)},
            "freshness": self.freshness,
            "truncated": self.truncated,
            "negative_evidence_admissible": False,
        }
        return {**deepcopy(value), "observation_identity": content_identity(value)}


def _resolved_candidate(endpoint: Mapping[str, Any]) -> str | None:
    resolution = endpoint.get("resolution")
    if (
        not isinstance(resolution, Mapping)
        or resolution.get("state") != "unique-candidate"
    ):
        return None
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        return None
    symbol = candidate.get("symbol_id")
    if isinstance(symbol, str) and symbol:
        return symbol
    return _qualified_symbol(candidate)


def _qualified_symbol(endpoint: object) -> str | None:
    """Use only revision-matched exact repository candidates, never a name join."""
    if not isinstance(endpoint, Mapping):
        return None
    binding = endpoint.get("source_binding")
    if isinstance(binding, Mapping) and binding.get("state") != "matching":
        return None
    return _resolved_candidate(endpoint)


def _correspondence_row(observation: Mapping[str, Any]) -> dict[str, Any]:
    keys: set[tuple[str, str, str]] = set()
    unresolved = 0
    for claim in observation.get("claims", []):
        if not isinstance(claim, Mapping):
            unresolved += 1
            continue
        source = _qualified_symbol(claim.get("source"))
        target = _qualified_symbol(claim.get("target"))
        if source is None or target is None:
            unresolved += 1
        else:
            keys.add((str(claim["kind"]), source, target))
    return {
        "producer": observation["producer"],
        "capture_identity": observation["capture_identity"],
        "scope": observation["scope"],
        "configuration_identity": observation["configuration_identity"],
        "qualified_claims": sorted(keys),
        "unresolved_claims": unresolved,
        "complete": (
            observation["collection_state"] == "fresh-complete"
            and observation["freshness"] == "current"
            and not observation["truncated"]
            and observation["accounting"].get("denied_or_unadmitted", 0) == 0
            and unresolved == 0
        ),
    }


def _correspondence_pair(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any]:
    a = set(tuple(x) for x in left["qualified_claims"])
    b = set(tuple(x) for x in right["qualified_claims"])
    aligned = sorted(a & b)
    distinct = sorted(a ^ b)
    return {
        "producers": [left["producer"], right["producer"]],
        "captures": [left["capture_identity"], right["capture_identity"]],
        "aligned_claims": [list(row) for row in aligned[:32]],
        "distinct_observed_claims": [list(row) for row in distinct[:32]],
        "aligned_omitted": max(0, len(aligned) - 32),
        "distinct_omitted": max(0, len(distinct) - 32),
        "semantic_authority": "direct-producer-claim-correspondence-only",
        "absence_or_conflict_inferred": False,
    }


def producer_claim_correspondence(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe qualified producer claim overlap without inferring truth or absence."""
    rows = [_correspondence_row(row) for row in observations]
    comparable_pairs: list[dict[str, Any]] = []
    incompatible_pairs = 0
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if left["producer"] == right["producer"]:
                continue
            if not left["complete"] or not right["complete"]:
                incompatible_pairs += 1
                continue
            comparable_pairs.append(_correspondence_pair(left, right))
    return {
        "schema": "hashmarks.semantic-relationship-correspondence.v1",
        "pairs": comparable_pairs[:32],
        "omitted_pairs": max(0, len(comparable_pairs) - 32),
        "incompatible_pairs": incompatible_pairs,
        "unresolved_claims": sum(row["unresolved_claims"] for row in rows),
        "negative_evidence_admissible": False,
        "authority": "descriptive-producer-claims-only",
        "execution_effect": "none",
    }


def finish_observation(
    target: str,
    repository: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    retained = [deepcopy(dict(row)) for row in observations[:OBSERVATION_LIMIT]]
    omitted = max(0, len(observations) - len(retained))
    value = {
        "schema": OBSERVATION_SCHEMA,
        "target": target,
        "repository": dict(repository),
        "authority": AUTHORITY,
        "execution_effect": "none",
        "negative_evidence_admissible": False,
        "observations": retained,
        "producer_correspondence": producer_claim_correspondence(retained),
        "coverage": {
            "retained_observations": len(retained),
            "omitted_observations": omitted,
            "bound_reasons": ["observation-count-bound"] if omitted else [],
        },
        "bounds": {
            "observations": OBSERVATION_LIMIT,
            "claims_per_observation": CLAIM_LIMIT,
            "candidates_per_resolution": CANDIDATE_LIMIT,
            "packet_bytes": PACKET_MAX_BYTES,
        },
    }
    # Byte bounds reduce the returned observation, never its qualification.
    while (
        len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        > PACKET_MAX_BYTES - 100
    ):
        if not retained:
            raise ValueError("relationship qualification exceeds packet byte bound")
        if "packet-byte-bound" not in value["coverage"]["bound_reasons"]:
            value["coverage"]["bound_reasons"].append("packet-byte-bound")
        last = retained[-1]
        if last["claims"]:
            keep = len(last["claims"]) // 2
            accounting = last["accounting"]
            accounting["packet_byte_omitted_claims"] = (
                accounting.get("packet_byte_omitted_claims", 0)
                + len(last["claims"])
                - keep
            )
            last["claims"] = last["claims"][:keep]
            accounting["retained"] = keep
            last["truncated"] = True
            last["observation_identity"] = content_identity(
                {
                    key: item
                    for key, item in last.items()
                    if key != "observation_identity"
                }
            )
        else:
            retained.pop()
            value["coverage"]["omitted_observations"] += 1
            value["coverage"]["retained_observations"] = len(retained)
    value["producer_correspondence"] = producer_claim_correspondence(retained)
    return {**value, "evidence_identity": content_identity(value)}


def _verify_identity(value: Mapping[str, Any], identity_field: str) -> None:
    semantic = {key: item for key, item in value.items() if key != identity_field}
    if value.get(identity_field) != content_identity(semantic):
        raise ValueError(
            f"relationship {identity_field} does not match retained evidence"
        )


def _validate_claim(claim: object, producer: str) -> None:
    if not isinstance(claim, Mapping) or claim.get("kind") not in RELATIONSHIP_KINDS:
        raise ValueError("invalid direct relationship claim")
    if claim.get("producer") != producer or claim.get("authority") != AUTHORITY:
        raise ValueError("relationship claim authority or producer mismatch")
    if claim.get("negative_evidence_admissible") is not False:
        raise ValueError("relationship claims cannot prove negative evidence")
    for endpoint in ("source", "target"):
        value = claim.get(endpoint)
        if not isinstance(value, Mapping) or not isinstance(value.get("key"), Mapping):
            raise ValueError("relationship claim must preserve endpoint identity")
        _validate_endpoint(value)
    if claim.get("identity") != claim_identity(claim):
        raise ValueError("relationship fact identity does not match retained claim")


def validate_relationship_observation(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = portable_copy(dict(payload), maximum=PACKET_MAX_BYTES)
    if value.get("schema") != OBSERVATION_SCHEMA or value.get("authority") != AUTHORITY:
        raise ValueError("invalid relationship observation schema or authority")
    if (
        value.get("execution_effect") != "none"
        or value.get("negative_evidence_admissible") is not False
    ):
        raise ValueError(
            "relationship observation cannot grant execution or absence authority"
        )
    _verify_identity(value, "evidence_identity")
    _validate_observation_context(value)
    observations = value.get("observations")
    if not isinstance(observations, list) or len(observations) > OBSERVATION_LIMIT:
        raise ValueError("invalid relationship observation count")
    for observation in observations:
        _validate_producer_observation(observation, value["target"])
    if "producer_correspondence" in value and value[
        "producer_correspondence"
    ] != producer_claim_correspondence(value["observations"]):
        raise ValueError(
            "relationship cross-producer correspondence does not match claims"
        )
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping) or coverage.get(
        "retained_observations"
    ) != len(observations):
        raise ValueError("relationship coverage contradicts retained observations")
    if (
        type(coverage.get("omitted_observations")) is not int
        or coverage["omitted_observations"] < 0
    ):
        raise ValueError("invalid omitted relationship observation count")
    return value


def _validate_producer_observation(observation: object, subject: str) -> None:
    if not isinstance(observation, Mapping):
        raise ValueError("relationship producer observation must be an object")
    _verify_identity(observation, "observation_identity")
    producer = bounded_token(observation.get("producer"), "producer")
    if (
        observation.get("collection_state") not in COLLECTION_STATES
        or observation.get("freshness") not in ("current", "stale", "unknown")
        or type(observation.get("truncated")) is not bool
    ):
        raise ValueError("invalid relationship collection or freshness state")
    if not isinstance(observation.get("scope"), Mapping) or not isinstance(
        observation.get("capability"), Mapping
    ):
        raise ValueError("relationship observations require scope and capability")
    _validate_producer_context(observation, subject)
    claims = observation.get("claims")
    if not isinstance(claims, list) or len(claims) > CLAIM_LIMIT:
        raise ValueError("invalid relationship claim count")
    for claim in claims:
        _validate_claim(claim, producer)
    _validate_hover_context(observation, claims)
    _validate_accounting(observation, len(claims))
    if observation.get("negative_evidence_admissible") is not False:
        raise ValueError("producer observation cannot prove negative evidence")


def _validate_hover_context(
    observation: Mapping[str, Any], claims: list[dict[str, Any]]
) -> None:
    capability = observation["capability"]
    scope = observation["scope"]
    if (
        scope.get("method") == "textDocument/hover"
        or capability.get("observed_operation") == "textDocument/hover"
    ):
        if (
            scope.get("method") != "textDocument/hover"
            or capability.get("observed_operation") != "textDocument/hover"
            or claims
        ):
            raise ValueError("LSP hover cannot assert relationship edges")
        # Imported at packet-validation time to avoid the source-resolver cycle.
        from .lsp_hover_capture import validate_hover_observation

        validate_hover_observation(
            capability.get("hover_observation"),
            response_error=capability.get("response_error"),
        )
    elif "hover_observation" in capability:
        raise ValueError("non-hover relationship cannot carry hover evidence")


def _validate_producer_context(observation: Mapping[str, Any], subject: str) -> None:
    bounded_token(observation.get("capture_identity"), "capture_identity")
    configuration = observation.get("configuration_identity")
    if configuration is not None:
        bounded_token(configuration, "configuration_identity")
    if observation["scope"].get("subject") != subject:
        raise ValueError("relationship producer scope contradicts query subject")
    if observation["capability"].get("authority") != "producer-claimed":
        raise ValueError(
            "relationship capability authority must remain producer-claimed"
        )


def _validate_accounting(observation: Mapping[str, Any], retained: int) -> None:
    accounting = observation.get("accounting")
    if not isinstance(accounting, Mapping) or accounting.get("retained") != retained:
        raise ValueError("relationship accounting contradicts retained claims")
    for count in accounting.values():
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError("invalid relationship accounting count")
    if "received" in accounting and accounting["received"] != sum(
        accounting.get(key, 0)
        for key in (
            "retained",
            "duplicates",
            "denied_or_unadmitted",
            "omitted_locations",
            "packet_byte_omitted_claims",
        )
    ):
        raise ValueError(
            "relationship location accounting does not conserve received claims"
        )
    bindings = observation.get("source_bindings")
    if not isinstance(bindings, list):
        raise ValueError("relationship source bindings must be retained")
    for binding in bindings:
        _validate_binding(binding)


def _validate_observation_context(value: Mapping[str, Any]) -> None:
    subject = bounded_token(value.get("target"), "target")
    path, separator, name = subject.partition("::")
    if (
        not separator
        or not name
        or normalize_relative_path(path, allow_root=False) != path
    ):
        raise ValueError("relationship subject must be an exact repository symbol")
    repository = value.get("repository")
    if (
        not isinstance(repository, Mapping)
        or type(repository.get("generation")) is not int
        or repository["generation"] < 0
    ):
        raise ValueError("invalid relationship repository binding")
    if repository.get("freshness") not in ("current", "stale", "unknown"):
        raise ValueError("invalid relationship repository freshness")
    for key in ("scope_identity", "content_identity", "observer_identity"):
        bounded_token(repository.get(key), key)


def _validate_binding(binding: object) -> None:
    if not isinstance(binding, Mapping):
        raise ValueError("relationship source binding must be an object")
    path = binding.get("path")
    if (
        not isinstance(path, str)
        or normalize_relative_path(path, allow_root=False) != path
    ):
        raise ValueError("invalid relationship source path")
    left, right = binding.get("claimed_revision"), binding.get("observed_revision")
    for revision in (left, right):
        if revision is not None and (
            not isinstance(revision, str) or not _DIGEST.fullmatch(revision)
        ):
            raise ValueError("invalid relationship source revision")
    state = (
        "unknown"
        if left is None or right is None
        else "matching"
        if left == right
        else "different"
    )
    if (
        binding.get("state") != state
        or binding.get("authority")
        != "producer-claim-to-stable-member-correspondence-only"
    ):
        raise ValueError("relationship source state contradicts revision claims")


def _validate_endpoint(value: Mapping[str, Any]) -> None:
    if not value["key"]:
        raise ValueError("relationship endpoint identity cannot be empty")
    if "source_binding" in value:
        _validate_binding(value["source_binding"])
    resolution = value.get("resolution")
    if resolution is None:
        return
    _validate_resolution(resolution)


def _validate_resolution(resolution: object) -> None:
    if (
        not isinstance(resolution, Mapping)
        or resolution.get("negative_evidence_admissible") is not False
    ):
        raise ValueError("invalid relationship target resolution")
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > CANDIDATE_LIMIT:
        raise ValueError("invalid relationship candidate count")
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("relationship candidate must be an object")
        if "key" in candidate:
            _validate_endpoint(candidate)
        elif "source_binding" in candidate:
            _validate_binding(candidate["source_binding"])
    if resolution.get("state") == "unique-candidate":
        _validate_unique_candidate(resolution, candidates)


def _validate_unique_candidate(
    resolution: Mapping[str, Any], candidates: list[Mapping[str, Any]]
) -> None:
    if len(candidates) != 1 or resolution.get("truncated") is not False:
        raise ValueError("bounded relationship candidates cannot establish uniqueness")
    binding = candidates[0].get("source_binding")
    if not isinstance(binding, Mapping) or binding.get("state") != "matching":
        raise ValueError("unique relationship candidate requires source correspondence")


def compact_relationships(payload: Mapping[str, Any]) -> dict[str, Any]:
    claims = [claim for row in payload["observations"] for claim in row["claims"]]
    return {
        "authority": AUTHORITY,
        "subject": payload["target"],
        "observation_identity": payload["evidence_identity"],
        "observed_relationship_count": len(claims),
        "claims": [_compact_claim(claim) for claim in claims[:COMPACT_CLAIM_LIMIT]],
        "omitted_from_presentation": max(0, len(claims) - COMPACT_CLAIM_LIMIT),
        "qualifications": [
            _compact_qualification(row) for row in payload["observations"]
        ],
        "coverage": deepcopy(payload["coverage"]),
        "negative_evidence_admissible": False,
        "detail_surface": "structural_locality",
        "detail_arguments": {
            "target": payload["target"],
            "result_mode": "relationships",
        },
    }


def _compact_qualification(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{
            key: deepcopy(value)
            for key, value in row.items()
            if key not in ("claims", "source_bindings")
        },
        "source_bindings": deepcopy(row["source_bindings"][:4]),
        "source_bindings_omitted_from_presentation": max(
            0, len(row["source_bindings"]) - 4
        ),
    }


def _compact_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(claim))
    for endpoint in ("source", "target"):
        resolution = value[endpoint].get("resolution")
        if not isinstance(resolution, dict):
            continue
        candidates = resolution.get("candidates", [])
        resolution["omitted_from_presentation"] = max(0, len(candidates) - 4)
        resolution["candidates"] = candidates[:4]
        for candidate in resolution["candidates"]:
            nested = candidate.get("resolution")
            if isinstance(nested, dict):
                rows = nested.get("candidates", [])
                nested["omitted_from_presentation"] = max(0, len(rows) - 4)
                nested["candidates"] = rows[:4]
    return value
