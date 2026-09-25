from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA = "hashmarks.repository-declarations.v1"
_DELTA_SCHEMA = "hashmarks.repository-declarations-delta.v1"
_MAX_GROUPS = 128
_MAX_DECLARATIONS = 256
_MAX_EXPECTED_PER_GROUP = 256
_GROUP_KEYS = frozenset(
    {"group_id", "concept", "scope", "correspondence", "declarations", "coverage"}
)
_DECLARATION_KEYS = frozenset(
    {"declaration_id", "value_state", "value", "candidate_values", "producer", "evidence"}
)
_CORRESPONDENCE_KEYS = frozenset({"state", "basis"})
_COVERAGE_KEYS = frozenset(
    {"state", "truncation", "expected_declaration_ids", "scope", "provenance"}
)


class RepositoryDeclarationsMixin:
    """Represent producer-neutral declarations of the same conceptual repository fact.

    The declaration provider owns semantic extraction and correspondence claims.
    Hashmarks owns exact repository evidence, deterministic identity, comparison,
    admissible absence, ambiguity preservation, freshness, and factual deltas.
    """

    @staticmethod
    def _declaration_json(value: object, *, name: str) -> object:
        try:
            encoded = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain JSON-compatible values") from exc
        return json.loads(encoded)

    @staticmethod
    def _declaration_mapping(value: object, *, name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
        return value

    @staticmethod
    def _reject_unknown(
        raw: Mapping[str, object], *, allowed: frozenset[str], name: str
    ) -> None:
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")

    @staticmethod
    def _required_text(value: object, *, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @classmethod
    def _correspondence(cls, raw: object) -> dict[str, object]:
        row = cls._declaration_mapping(raw, name="correspondence")
        cls._reject_unknown(row, allowed=_CORRESPONDENCE_KEYS, name="correspondence")
        state = cls._required_text(row.get("state"), name="correspondence.state")
        if state not in {"declared", "ambiguous", "unresolved"}:
            raise ValueError(
                "correspondence.state must be declared, ambiguous, or unresolved"
            )
        basis = cls._declaration_json(row.get("basis", {}), name="correspondence.basis")
        if not isinstance(basis, dict):
            raise ValueError("correspondence.basis must be an object")
        return {"state": state, "basis": basis}

    @classmethod
    def _coverage(cls, raw: object) -> dict[str, object]:
        row = cls._declaration_mapping(raw, name="coverage")
        cls._reject_unknown(row, allowed=_COVERAGE_KEYS, name="coverage")
        state = cls._required_text(row.get("state"), name="coverage.state")
        truncation = cls._required_text(
            row.get("truncation"), name="coverage.truncation"
        )
        if state not in {"complete", "incomplete", "unknown"}:
            raise ValueError("coverage.state must be complete, incomplete, or unknown")
        if truncation not in {"complete", "truncated", "unknown"}:
            raise ValueError(
                "coverage.truncation must be complete, truncated, or unknown"
            )
        if state == "complete" and truncation != "complete":
            raise ValueError(
                "complete declaration coverage requires truncation=complete"
            )
        expected_raw = row.get("expected_declaration_ids", [])
        if not isinstance(expected_raw, Sequence) or isinstance(
            expected_raw, (str, bytes)
        ):
            raise ValueError("coverage.expected_declaration_ids must be a list")
        if len(expected_raw) > _MAX_EXPECTED_PER_GROUP:
            raise ValueError(
                "coverage.expected_declaration_ids exceeds "
                f"{_MAX_EXPECTED_PER_GROUP} entries"
            )
        expected = [
            cls._required_text(value, name="expected declaration id")
            for value in expected_raw
        ]
        if len(set(expected)) != len(expected):
            raise ValueError("coverage.expected_declaration_ids contains duplicates")
        scope = cls._declaration_json(row.get("scope", {}), name="coverage.scope")
        provenance = cls._declaration_json(
            row.get("provenance", {}), name="coverage.provenance"
        )
        if not isinstance(scope, dict) or not isinstance(provenance, dict):
            raise ValueError("coverage scope/provenance must be objects")
        return {
            "state": state,
            "truncation": truncation,
            "expected_declaration_ids": sorted(expected),
            "scope": scope,
            "provenance": provenance,
            "authority": "provider-claimed",
        }

    @classmethod
    def _declaration(
        cls, raw: object, *, group_id: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        row = cls._declaration_mapping(raw, name="declaration")
        cls._reject_unknown(row, allowed=_DECLARATION_KEYS, name="declaration")
        declaration_id = cls._required_text(
            row.get("declaration_id"), name="declaration_id"
        )
        value_state = cls._required_text(row.get("value_state"), name="value_state")
        if value_state not in {"resolved", "ambiguous", "unresolved"}:
            raise ValueError(
                "value_state must be resolved, ambiguous, or unresolved"
            )
        producer = cls._declaration_json(row.get("producer", {}), name="producer")
        if not isinstance(producer, dict):
            raise ValueError("producer must be an object")
        evidence = row.get("evidence")
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
            raise ValueError("declaration evidence must be a list")
        if not evidence:
            raise ValueError("each declaration requires exact repository evidence")
        normalized_evidence: list[dict[str, object]] = []
        for item in evidence:
            if not isinstance(item, Mapping):
                raise ValueError("each declaration evidence item must be an object")
            normalized_evidence.append(dict(item))

        result: dict[str, object] = {
            "declaration_id": declaration_id,
            "value_state": value_state,
            "producer": producer,
        }
        if value_state == "resolved":
            if "value" not in row:
                raise ValueError("resolved declaration requires value")
            if "candidate_values" in row:
                raise ValueError(
                    "resolved declaration must not declare candidate_values"
                )
            result["value"] = cls._declaration_json(
                row["value"], name="declaration value"
            )
        elif value_state == "ambiguous":
            if "value" in row:
                raise ValueError("ambiguous declaration must not declare value")
            candidates = row.get("candidate_values")
            if not isinstance(candidates, Sequence) or isinstance(
                candidates, (str, bytes)
            ):
                raise ValueError(
                    "ambiguous declaration requires candidate_values list"
                )
            if len(candidates) < 2:
                raise ValueError(
                    "ambiguous declaration requires at least two candidate values"
                )
            result["candidate_values"] = [
                cls._declaration_json(value, name="candidate value")
                for value in candidates
            ]
        else:
            if "value" in row or "candidate_values" in row:
                raise ValueError(
                    "unresolved declaration must not declare value or candidate_values"
                )

        binding_id = f"declaration:{group_id}:{declaration_id}"
        binding = {"binding_id": binding_id, "evidence": normalized_evidence}
        result["binding_id"] = binding_id
        return result, binding

    @staticmethod
    def _comparison(
        declarations: Sequence[Mapping[str, object]],
        correspondence: Mapping[str, object],
    ) -> dict[str, object]:
        if correspondence.get("state") != "declared":
            return {
                "state": "ambiguous",
                "reason": "correspondence-not-uniquely-declared",
                "distinct_values": [],
            }
        nonresolved = [
            str(row["declaration_id"])
            for row in declarations
            if row.get("value_state") != "resolved"
        ]
        if nonresolved:
            return {
                "state": "ambiguous",
                "reason": "one-or-more-values-not-resolved",
                "ambiguous_declaration_ids": sorted(nonresolved),
                "distinct_values": [],
            }
        if len(declarations) < 2:
            return {
                "state": "insufficient",
                "reason": "fewer-than-two-resolved-declarations",
                "distinct_values": [
                    declarations[0]["value"]
                ]
                if declarations
                else [],
            }
        by_json: dict[str, object] = {}
        for row in declarations:
            value = row["value"]
            key = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            by_json.setdefault(key, value)
        distinct = [by_json[key] for key in sorted(by_json)]
        return {
            "state": "equivalent" if len(distinct) == 1 else "differing",
            "distinct_values": distinct,
        }

    @staticmethod
    def _absence(
        declarations: Sequence[Mapping[str, object]],
        coverage: Mapping[str, object],
    ) -> dict[str, object]:
        expected = set(coverage.get("expected_declaration_ids") or [])
        present = {str(row["declaration_id"]) for row in declarations}
        unseen = sorted(expected - present)
        if not expected:
            return {
                "state": "not-assessed",
                "missing_declaration_ids": [],
                "unseen_expected_declaration_ids": [],
            }
        if not unseen:
            return {
                "state": "none",
                "missing_declaration_ids": [],
                "unseen_expected_declaration_ids": [],
            }
        if (
            coverage.get("state") == "complete"
            and coverage.get("truncation") == "complete"
        ):
            return {
                "state": "present",
                "missing_declaration_ids": unseen,
                "unseen_expected_declaration_ids": [],
            }
        return {
            "state": "unknown",
            "missing_declaration_ids": [],
            "unseen_expected_declaration_ids": unseen,
            "reason": "coverage-does-not-authorize-negative-evidence",
        }

    def _declaration_group(
        self,
        raw: object,
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        group = self._declaration_mapping(raw, name="declaration group")
        self._reject_unknown(group, allowed=_GROUP_KEYS, name="declaration group")
        group_id = self._required_text(group.get("group_id"), name="group_id")
        concept = self._declaration_json(group.get("concept"), name="concept")
        scope = self._declaration_json(group.get("scope", {}), name="scope")
        if not isinstance(concept, dict) or not isinstance(scope, dict):
            raise ValueError("concept and scope must be objects")
        correspondence = self._correspondence(group.get("correspondence", {}))
        coverage = self._coverage(group.get("coverage", {}))

        raw_declarations = group.get("declarations")
        if not isinstance(raw_declarations, Sequence) or isinstance(
            raw_declarations, (str, bytes)
        ):
            raise ValueError("declarations must be a list")
        declarations: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw_declaration in raw_declarations:
            normalized, _binding = self._declaration(
                raw_declaration, group_id=group_id
            )
            declaration_id = str(normalized["declaration_id"])
            if declaration_id in seen:
                raise ValueError(
                    f"duplicate declaration_id in group {group_id}: {declaration_id}"
                )
            seen.add(declaration_id)
            binding = binding_rows[str(normalized["binding_id"])]
            definition = {
                "group_id": group_id,
                "concept": concept,
                "scope": scope,
                "declaration_id": declaration_id,
            }
            observation = {
                **definition,
                "value_state": normalized["value_state"],
                **(
                    {"value": normalized["value"]}
                    if "value" in normalized
                    else {}
                ),
                **(
                    {"candidate_values": normalized["candidate_values"]}
                    if "candidate_values" in normalized
                    else {}
                ),
                "producer": normalized["producer"],
                "binding_observation_identity": binding[
                    "binding_observation_identity"
                ],
            }
            declarations.append(
                {
                    **normalized,
                    "declaration_definition_identity": "sha256:"
                    + self._packet_digest(
                        "hashmarks.repository-declaration-definition.v1",
                        definition,
                    ),
                    "declaration_observation_identity": "sha256:"
                    + self._packet_digest(
                        "hashmarks.repository-declaration-observation.v1",
                        observation,
                    ),
                }
            )
        declarations.sort(key=lambda row: str(row["declaration_id"]))
        expected = set(coverage["expected_declaration_ids"])
        unknown_expected = sorted(expected - seen)
        comparison = self._comparison(declarations, correspondence)
        absence = self._absence(declarations, coverage)
        definition_payload = {
            "group_id": group_id,
            "concept": concept,
            "scope": scope,
            "expected_declaration_ids": coverage["expected_declaration_ids"],
        }
        observation_payload = {
            **definition_payload,
            "correspondence": correspondence,
            "coverage": coverage,
            "declarations": declarations,
            "comparison": comparison,
            "absence": absence,
        }
        return {
            **observation_payload,
            "group_definition_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-group-definition.v1",
                definition_payload,
            ),
            "group_observation_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-group-observation.v1",
                observation_payload,
            ),
            "unseen_expected_declaration_ids": unknown_expected,
        }

    @classmethod
    def _normalize_request(
        cls, groups: Sequence[Mapping[str, object]]
    ) -> tuple[list[Mapping[str, object]], list[dict[str, object]]]:
        if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
            raise ValueError("groups must be a sequence")
        if len(groups) > _MAX_GROUPS:
            raise ValueError(f"groups exceeds {_MAX_GROUPS} entries")
        normalized_groups: list[Mapping[str, object]] = []
        bindings: list[dict[str, object]] = []
        seen_groups: set[str] = set()
        declaration_count = 0
        for raw_group in groups:
            if not isinstance(raw_group, Mapping):
                raise ValueError("each declaration group must be an object")
            cls._reject_unknown(
                raw_group, allowed=_GROUP_KEYS, name="declaration group"
            )
            group_id = cls._required_text(raw_group.get("group_id"), name="group_id")
            if group_id in seen_groups:
                raise ValueError(f"duplicate group_id: {group_id}")
            seen_groups.add(group_id)
            raw_declarations = raw_group.get("declarations")
            if not isinstance(raw_declarations, Sequence) or isinstance(
                raw_declarations, (str, bytes)
            ):
                raise ValueError("declarations must be a list")
            group_seen: set[str] = set()
            for raw_declaration in raw_declarations:
                normalized, binding = cls._declaration(
                    raw_declaration, group_id=group_id
                )
                declaration_id = str(normalized["declaration_id"])
                if declaration_id in group_seen:
                    raise ValueError(
                        f"duplicate declaration_id in group {group_id}: {declaration_id}"
                    )
                group_seen.add(declaration_id)
                bindings.append(binding)
                declaration_count += 1
            normalized_groups.append(raw_group)
        if declaration_count > _MAX_DECLARATIONS:
            raise ValueError(
                f"declaration request exceeds {_MAX_DECLARATIONS} declarations"
            )
        return normalized_groups, bindings

    def _declaration_packet_identity(self, packet: Mapping[str, object]) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        payload = {
            key: value
            for key, value in packet.items()
            if key not in {"observation_identity", "delta_from_previous"}
        }
        return "sha256:" + self._packet_digest(_SCHEMA, payload)

    def _validate_previous_declarations(
        self, previous: Mapping[str, object]
    ) -> None:
        if previous.get("schema") != _SCHEMA:
            raise ValueError(f"previous observation must use schema {_SCHEMA}")
        identity = previous.get("observation_identity")
        if not isinstance(identity, str) or identity != self._declaration_packet_identity(
            previous
        ):
            raise ValueError("previous declaration observation identity mismatch")

    @staticmethod
    def _declaration_delta(
        previous: Mapping[str, object],
        current: Mapping[str, object],
    ) -> dict[str, object]:
        before = {
            str(row["group_id"]): row
            for row in previous.get("groups", [])
            if isinstance(row, Mapping)
        }
        after = {
            str(row["group_id"]): row
            for row in current.get("groups", [])
            if isinstance(row, Mapping)
        }
        changed: list[dict[str, object]] = []
        for group_id in sorted(set(before) & set(after)):
            old = before[group_id]
            new = after[group_id]
            if old.get("group_observation_identity") == new.get(
                "group_observation_identity"
            ):
                continue
            old_declarations = {
                str(row["declaration_id"]): row
                for row in old.get("declarations", [])
                if isinstance(row, Mapping)
            }
            new_declarations = {
                str(row["declaration_id"]): row
                for row in new.get("declarations", [])
                if isinstance(row, Mapping)
            }
            shared = set(old_declarations) & set(new_declarations)
            value_changed = sorted(
                declaration_id
                for declaration_id in shared
                if (
                    old_declarations[declaration_id].get("value_state"),
                    old_declarations[declaration_id].get("value"),
                    old_declarations[declaration_id].get("candidate_values"),
                )
                != (
                    new_declarations[declaration_id].get("value_state"),
                    new_declarations[declaration_id].get("value"),
                    new_declarations[declaration_id].get("candidate_values"),
                )
            )
            evidence_changed = sorted(
                declaration_id
                for declaration_id in shared
                if old_declarations[declaration_id].get(
                    "declaration_observation_identity"
                )
                != new_declarations[declaration_id].get(
                    "declaration_observation_identity"
                )
                and declaration_id not in value_changed
            )
            changed.append(
                {
                    "group_id": group_id,
                    "definition_changed": old.get("group_definition_identity")
                    != new.get("group_definition_identity"),
                    "added_declaration_ids": sorted(
                        set(new_declarations) - set(old_declarations)
                    ),
                    "removed_declaration_ids": sorted(
                        set(old_declarations) - set(new_declarations)
                    ),
                    "value_changed_declaration_ids": value_changed,
                    "evidence_or_provenance_changed_declaration_ids": evidence_changed,
                    "comparison_changed": old.get("comparison")
                    != new.get("comparison"),
                    "absence_changed": old.get("absence") != new.get("absence"),
                    "correspondence_changed": old.get("correspondence")
                    != new.get("correspondence"),
                    "coverage_changed": old.get("coverage") != new.get("coverage"),
                }
            )
        return {
            "schema": _DELTA_SCHEMA,
            "added_group_ids": sorted(set(after) - set(before)),
            "removed_group_ids": sorted(set(before) - set(after)),
            "changed_groups": changed,
            "repository_changed": previous.get("repository")
            != current.get("repository"),
            "observer_changed": previous.get("observer") != current.get("observer"),
            "interpretation": "factual-only",
        }

    def repository_declarations(
        self,
        groups: Sequence[Mapping[str, object]],
        *,
        previous_observation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Qualify cross-artifact declarations without choosing a winning value."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized_groups, bindings = self._normalize_request(groups)
        evidence_packet = self.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        binding_rows = {
            str(row["binding_id"]): row for row in evidence_packet["bindings"]
        }
        projected = [
            self._declaration_group(raw, binding_rows)
            for raw in normalized_groups
        ]
        projected.sort(key=lambda row: str(row["group_id"]))
        packet: dict[str, object] = {
            "schema": _SCHEMA,
            "observer": evidence_packet["observer"],
            "repository": evidence_packet["repository"],
            "groups": projected,
            "repository_evidence": evidence_packet,
            "bounds": {
                "max_groups": _MAX_GROUPS,
                "max_declarations": _MAX_DECLARATIONS,
                "max_expected_declarations_per_group": _MAX_EXPECTED_PER_GROUP,
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "correspondence_authority": "provider-claimed",
            "interpretation_authority": "consumer-owned",
            "winner": "not-selected",
        }
        packet["observation_identity"] = self._declaration_packet_identity(packet)
        if previous_observation is not None:
            if not isinstance(previous_observation, Mapping):
                raise ValueError("previous_observation must be an object")
            self._validate_previous_declarations(previous_observation)
            packet["delta_from_previous"] = self._declaration_delta(
                previous_observation, packet
            )
        return packet
