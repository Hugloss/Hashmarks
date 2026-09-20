from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ._version import __version__
from .producer_identity import native_producer_implementation_identity
from .qualification_classification import (
    ALLOWED_KINDS,
    classify_nodeids,
)
from .test_shards import (
    _nodeids,
    node_membership_identity,
)
from .validation_inputs import require_mapping_for_validation

if TYPE_CHECKING:
    from pathlib import Path

UNIT_SCHEMA = "hashmarks.qualification-owner-unit.v2"
PLAN_SCHEMA = "hashmarks.qualification-owner-plan.v2"
COVERAGE_SCHEMA = "hashmarks.external-qualification-coverage.v1"
COVERAGE_PROVENANCE_SCHEMA = "hashmarks.qualification-coverage-provenance.v1"
EXTERNAL_RESULT_SCHEMA = "hashmarks.external-qualification-result.v1"
HANDOFF_SCHEMA = "hashmarks.native-qualification-handoff.v1"

_EXECUTION_FORBIDDEN = frozenset(
    {
        "timeout",
        "timeout_seconds",
        "deadline",
        "retry",
        "retry_count",
        "workers",
        "worker_count",
        "concurrency",
        "schedule",
        "command",
        "argv",
        "process_id",
        "machine",
        "executor",
    }
)
_SHA256_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}:[0-9]+$")
_UNIT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "name",
        "kind",
        "nodeids",
        "membership_identity",
        "classification_identity",
        "preferred_granularity",
        "execution_authority",
        "result_authority",
        "certification_authority",
        "may_regroup",
        "unit_identity",
    }
)
_PLAN_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "producer",
        "repository_identity",
        "membership_identity",
        "classification_identity",
        "classification_policy_identity",
        "unit_count",
        "test_node_count",
        "units",
        "authority",
        "plan_identity",
    }
)
_HANDOFF_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "producer",
        "repository_identity",
        "membership_identity",
        "classification_identity",
        "classification_policy_identity",
        "plan_identity",
        "units",
        "provenance",
        "execution_authority",
        "result_authority",
        "certification_authority",
        "may_regroup",
        "handoff_identity",
    }
)
_EXTERNAL_AUTHORITY_FIELDS = (
    "execution_authority",
    "result_authority",
    "certification_authority",
)


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _identity(domain: str, value: Mapping[str, object]) -> str:
    digest = hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical_bytes(value))
    return "sha256:" + digest.hexdigest()


def _node_file(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def _unit_row(
    *,
    name: str,
    kind: str,
    nodeids: Sequence[str],
    preferred_granularity: str,
    classification_identity: str,
) -> dict[str, object]:
    members = tuple(sorted(nodeids))
    payload: dict[str, object] = {
        "schema": UNIT_SCHEMA,
        "name": name,
        "kind": kind,
        "nodeids": list(members),
        "membership_identity": node_membership_identity(members),
        "classification_identity": classification_identity,
        "preferred_granularity": preferred_granularity,
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
        "may_regroup": True,
    }
    payload["unit_identity"] = _identity(UNIT_SCHEMA, payload)
    return payload


def _qualification_owner_units_from_classification(
    all_nodes: Sequence[str],
    artifact: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    classification_identity = str(artifact["classification_identity"])
    rows = artifact.get("classifications")
    if not isinstance(rows, list):
        raise ValueError(
            "qualification classification artifact requires classifications"
        )
    classes = {
        str(row["nodeid"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("nodeid"), str)
    }
    ordinary: dict[str, list[str]] = defaultdict(list)
    units: list[dict[str, object]] = []

    for nodeid in all_nodes:
        row = classes[nodeid]
        kind = str(row["kind"])
        preferred = str(row["preferred_granularity"])
        if kind == "release-correctness" and preferred == "file":
            ordinary[_node_file(nodeid)].append(nodeid)
        else:
            units.append(
                _unit_row(
                    name=f"{kind}:{nodeid}",
                    kind=kind,
                    nodeids=(nodeid,),
                    preferred_granularity=preferred,
                    classification_identity=classification_identity,
                )
            )

    for path, members in sorted(ordinary.items()):
        units.append(
            _unit_row(
                name=f"release-correctness:{path}",
                kind="release-correctness",
                nodeids=members,
                preferred_granularity="file",
                classification_identity=classification_identity,
            )
        )
    return tuple(sorted(units, key=lambda row: str(row["name"])))


def qualification_owner_units(root: Path) -> tuple[dict[str, object], ...]:
    root = root.resolve()
    all_nodes = tuple(nodeid for nodeid, _weight in _nodeids(root))
    classification = classify_nodeids(root, all_nodes)
    return _qualification_owner_units_from_classification(all_nodes, classification)


def qualification_owner_plan(root: Path) -> dict[str, object]:
    root = root.resolve()
    all_nodes = tuple(nodeid for nodeid, _weight in _nodeids(root))
    classification = classify_nodeids(root, all_nodes)
    units = _qualification_owner_units_from_classification(all_nodes, classification)
    nodeids = [nodeid for unit in units for nodeid in unit["nodeids"]]
    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "producer": {
            "name": "hashmarks",
            "version": __version__,
            "implementation_identity": native_producer_implementation_identity(),
        },
        "repository_identity": classification["repository_identity"],
        "membership_identity": node_membership_identity(nodeids),
        "classification_identity": classification["classification_identity"],
        "classification_policy_identity": classification["policy_identity"],
        "unit_count": len(units),
        "test_node_count": len(nodeids),
        "units": list(units),
        "authority": {
            "classification": "hashmarks",
            "execution": "external",
            "result": "external",
            "certification": "external",
        },
    }
    payload["plan_identity"] = _identity(PLAN_SCHEMA, payload)
    return payload


def _forbidden_execution_fields(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in _EXECUTION_FORBIDDEN:
                found.append(key_text)
            found.extend(_forbidden_execution_fields(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_forbidden_execution_fields(child))
    return found


def _find_unit(
    plan: Mapping[str, object], unit_identity: object
) -> Mapping[str, object] | None:
    units = plan.get("units")
    if not isinstance(units, list):
        return None
    return next(
        (
            row
            for row in units
            if isinstance(row, Mapping) and row.get("unit_identity") == unit_identity
        ),
        None,
    )


def _valid_sha256_identity(value: object) -> bool:
    return isinstance(value, str) and _SHA256_IDENTITY.fullmatch(value) is not None


def _producer_reasons(producer: object) -> list[str]:
    if not isinstance(producer, Mapping):
        return ["invalid-qualification-producer"]
    reasons: list[str] = []
    if set(producer) != {"name", "version", "implementation_identity"}:
        reasons.append("qualification-producer-fields-mismatch")
    if producer.get("name") != "hashmarks":
        reasons.append("invalid-qualification-producer-name")
    if (
        not isinstance(producer.get("version"), str)
        or not str(producer.get("version")).strip()
    ):
        reasons.append("invalid-qualification-producer-version")
    if not _valid_sha256_identity(producer.get("implementation_identity")):
        reasons.append("invalid-qualification-producer-implementation-identity")
    try:
        _canonical_bytes(producer)
    except (TypeError, ValueError):
        reasons.append("qualification-producer-not-canonical-json")
    return reasons


def _unit_header_reasons(
    unit: Mapping[str, object],
) -> tuple[list[str], object, object, object]:
    reasons: list[str] = []
    if set(unit) != _UNIT_REQUIRED_FIELDS:
        reasons.append("qualification-unit-fields-mismatch")
    if unit.get("schema") != UNIT_SCHEMA:
        reasons.append("unsupported-qualification-unit-schema")
    name = unit.get("name")
    if not isinstance(name, str) or not name.strip():
        reasons.append("invalid-qualification-unit-name")
    kind = unit.get("kind")
    if kind not in ALLOWED_KINDS:
        reasons.append("invalid-qualification-unit-kind")
    preferred = unit.get("preferred_granularity")
    if preferred not in {"file", "singleton"}:
        reasons.append("invalid-qualification-unit-granularity")
    if (
        kind in {"process-sensitive", "empirical-benchmark"}
        and preferred != "singleton"
    ):
        reasons.append("qualification-unit-isolation-mismatch")
    return reasons, name, kind, preferred


def _unit_nodeid_reasons(
    unit: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    nodeids = unit.get("nodeids")
    if (
        not isinstance(nodeids, list)
        or not nodeids
        or not all(isinstance(nodeid, str) and nodeid for nodeid in nodeids)
    ):
        return ["invalid-qualification-unit-nodeids"], []

    normalized = list(nodeids)
    if normalized != sorted(set(normalized)):
        reasons.append("noncanonical-qualification-unit-nodeids")
    try:
        membership = node_membership_identity(normalized)
    except ValueError:
        membership = None
        reasons.append("invalid-qualification-unit-nodeids")
    if unit.get("membership_identity") != membership:
        reasons.append("qualification-unit-membership-identity-mismatch")
    return reasons, normalized


def _unit_classification_reasons(
    unit: Mapping[str, object],
    classification_identity: object | None,
) -> list[str]:
    reasons: list[str] = []
    unit_classification = unit.get("classification_identity")
    if not _valid_sha256_identity(unit_classification):
        reasons.append("invalid-qualification-unit-classification-identity")
    if (
        classification_identity is not None
        and unit_classification != classification_identity
    ):
        reasons.append("qualification-unit-classification-identity-mismatch")
    return reasons


def _unit_shape_reasons(
    *,
    name: object,
    kind: object,
    preferred: object,
    nodeids: list[str],
) -> list[str]:
    reasons: list[str] = []
    if preferred == "singleton" and nodeids:
        if len(nodeids) != 1 or name != f"{kind}:{nodeids[0]}":
            reasons.append("qualification-unit-singleton-shape-mismatch")
    if preferred == "file" and nodeids:
        files = {_node_file(nodeid) for nodeid in nodeids}
        if (
            kind != "release-correctness"
            or len(files) != 1
            or name != f"release-correctness:{next(iter(files))}"
        ):
            reasons.append("qualification-unit-file-shape-mismatch")
    return reasons


def _unit_authority_reasons(unit: Mapping[str, object]) -> list[str]:
    reasons = [
        f"qualification-unit-{field.replace('_', '-')}-must-be-external"
        for field in _EXTERNAL_AUTHORITY_FIELDS
        if unit.get(field) != "external"
    ]
    if unit.get("may_regroup") is not True:
        reasons.append("qualification-unit-may-regroup-must-be-true")
    if _forbidden_execution_fields(unit):
        reasons.append("qualification-unit-execution-policy-present")
    return reasons


def _unit_identity_reasons(unit: Mapping[str, object]) -> list[str]:
    payload = {key: value for key, value in unit.items() if key != "unit_identity"}
    reasons: list[str] = []
    try:
        expected = _identity(UNIT_SCHEMA, payload)
    except (TypeError, ValueError):
        expected = None
        reasons.append("qualification-unit-not-canonical-json")
    if expected is None or unit.get("unit_identity") != expected:
        reasons.append("qualification-unit-identity-mismatch")
    return reasons


def _unit_reasons(
    unit: object,
    *,
    classification_identity: object | None = None,
) -> list[str]:
    if not isinstance(unit, Mapping):
        return ["invalid-qualification-unit"]
    reasons, name, kind, preferred = _unit_header_reasons(unit)
    nodeid_reasons, nodeids = _unit_nodeid_reasons(unit)
    reasons.extend(nodeid_reasons)
    reasons.extend(_unit_classification_reasons(unit, classification_identity))
    reasons.extend(
        _unit_shape_reasons(
            name=name,
            kind=kind,
            preferred=preferred,
            nodeids=nodeids,
        )
    )
    reasons.extend(_unit_authority_reasons(unit))
    reasons.extend(_unit_identity_reasons(unit))
    return reasons


def _plan_header_reasons(
    plan: Mapping[str, object],
) -> tuple[list[str], object]:
    reasons: list[str] = []
    if set(plan) != _PLAN_REQUIRED_FIELDS:
        reasons.append("qualification-plan-fields-mismatch")
    if plan.get("schema") != PLAN_SCHEMA:
        reasons.append("unsupported-qualification-plan-schema")
    reasons.extend(_producer_reasons(plan.get("producer")))
    repository_identity = plan.get("repository_identity")
    if not isinstance(repository_identity, str) or not _REPOSITORY_IDENTITY.fullmatch(
        repository_identity
    ):
        reasons.append("invalid-qualification-repository-identity")
    classification_identity = plan.get("classification_identity")
    if not _valid_sha256_identity(classification_identity):
        reasons.append("invalid-qualification-classification-identity")
    if not _valid_sha256_identity(plan.get("classification_policy_identity")):
        reasons.append("invalid-qualification-classification-policy-identity")
    return reasons, classification_identity


def _plan_unit_reasons(
    units: object,
    *,
    classification_identity: object,
) -> tuple[list[str], list[str]]:
    if not isinstance(units, list) or not units:
        return ["invalid-qualification-units"], []

    reasons: list[str] = []
    nodeids: list[str] = []
    unit_names: list[str] = []
    unit_ids: list[str] = []
    for unit in units:
        reasons.extend(
            _unit_reasons(unit, classification_identity=classification_identity)
        )
        if not isinstance(unit, Mapping):
            continue
        if isinstance(unit.get("name"), str):
            unit_names.append(str(unit["name"]))
        if isinstance(unit.get("unit_identity"), str):
            unit_ids.append(str(unit["unit_identity"]))
        raw_nodeids = unit.get("nodeids")
        if isinstance(raw_nodeids, list):
            nodeids.extend(
                str(nodeid) for nodeid in raw_nodeids if isinstance(nodeid, str)
            )

    if unit_names != sorted(unit_names) or len(unit_names) != len(set(unit_names)):
        reasons.append("noncanonical-qualification-units")
    if len(unit_ids) != len(set(unit_ids)):
        reasons.append("duplicate-qualification-unit-identity")
    if len(nodeids) != len(set(nodeids)):
        reasons.append("duplicate-qualification-nodeid")
    return reasons, nodeids


def _plan_count_membership_reasons(
    plan: Mapping[str, object],
    *,
    units: object,
    nodeids: list[str],
) -> list[str]:
    reasons: list[str] = []
    unit_count = len(units) if isinstance(units, list) else 0
    if type(plan.get("unit_count")) is not int or plan.get("unit_count") != unit_count:
        reasons.append("qualification-unit-count-mismatch")
    if (
        type(plan.get("test_node_count")) is not int
        or plan.get("test_node_count") != len(nodeids)
    ):
        reasons.append("qualification-test-node-count-mismatch")
    if nodeids:
        try:
            membership = node_membership_identity(nodeids)
        except ValueError:
            membership = None
        if plan.get("membership_identity") != membership:
            reasons.append("qualification-membership-identity-mismatch")
    return reasons


def _plan_authority_identity_reasons(plan: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    if plan.get("authority") != {
        "classification": "hashmarks",
        "execution": "external",
        "result": "external",
        "certification": "external",
    }:
        reasons.append("qualification-plan-authority-mismatch")
    if _forbidden_execution_fields(plan):
        reasons.append("qualification-plan-execution-policy-present")
    payload = {key: value for key, value in plan.items() if key != "plan_identity"}
    try:
        expected = _identity(PLAN_SCHEMA, payload)
    except (TypeError, ValueError):
        expected = None
        reasons.append("qualification-plan-not-canonical-json")
    if expected is None or plan.get("plan_identity") != expected:
        reasons.append("qualification-plan-identity-mismatch")
    return reasons


def _qualification_plan_reasons(plan: object) -> list[str]:
    if not isinstance(plan, Mapping):
        return ["invalid-qualification-plan"]
    reasons, classification_identity = _plan_header_reasons(plan)
    units = plan.get("units")
    unit_reasons, nodeids = _plan_unit_reasons(
        units,
        classification_identity=classification_identity,
    )
    reasons.extend(unit_reasons)
    reasons.extend(_plan_count_membership_reasons(plan, units=units, nodeids=nodeids))
    reasons.extend(_plan_authority_identity_reasons(plan))
    return reasons


def _executed_membership_identity(coverage: Mapping[str, object]) -> str | None:
    executed = coverage.get("executed_nodeids")
    if not isinstance(executed, list):
        return None
    try:
        return node_membership_identity(executed)
    except ValueError:
        return None


def _coverage_shape_reasons(coverage: Mapping[str, object]) -> list[str]:
    required = {
        "schema",
        "producer",
        "repository_identity",
        "plan_identity",
        "unit_identity",
        "membership_identity",
        "executed_nodeids",
        "producer_implementation_identity",
        "provenance_identity",
        "execution_authority",
        "result_authority",
        "certification_authority",
    }
    reasons: list[str] = []
    if set(coverage) != required:
        reasons.append("coverage-fields-mismatch")
    if coverage.get("schema") != COVERAGE_SCHEMA:
        reasons.append("unsupported-coverage-schema")
    if _forbidden_execution_fields(coverage):
        reasons.append("execution-policy-present")
    return reasons


def _coverage_authority_reasons(coverage: Mapping[str, object]) -> list[str]:
    fields = ("execution_authority", "result_authority", "certification_authority")
    return [
        f"{field.replace('_', '-')}-must-be-external"
        for field in fields
        if coverage.get(field) != "external"
    ]


def _external_coverage_producer_reasons(producer: object) -> list[str]:
    if not isinstance(producer, Mapping):
        return ["invalid-external-coverage-producer"]
    reasons: list[str] = []
    name = producer.get("name")
    if not isinstance(name, str) or not name.strip():
        reasons.append("invalid-external-coverage-producer-name")
    try:
        _canonical_bytes(producer)
    except (TypeError, ValueError):
        reasons.append("external-coverage-producer-not-canonical-json")
    return reasons


def _coverage_plan_reasons(
    plan: Mapping[str, object],
    coverage: Mapping[str, object],
) -> list[str]:
    checks = (
        ("repository_identity", "repository-identity-mismatch"),
        ("plan_identity", "plan-identity-mismatch"),
    )
    reasons = [
        reason for field, reason in checks if coverage.get(field) != plan.get(field)
    ]
    producer = plan.get("producer")
    expected = (
        producer.get("implementation_identity")
        if isinstance(producer, Mapping)
        else None
    )
    if coverage.get("producer_implementation_identity") != expected:
        reasons.append("producer-implementation-identity-mismatch")
    return reasons


def _coverage_unit_reasons(
    plan: Mapping[str, object],
    coverage: Mapping[str, object],
) -> list[str]:
    unit = _find_unit(plan, coverage.get("unit_identity"))
    if unit is None:
        return ["unknown-unit"]
    reasons: list[str] = []
    if coverage.get("membership_identity") != unit.get("membership_identity"):
        reasons.append("membership-identity-mismatch")
    if _executed_membership_identity(coverage) != unit.get("membership_identity"):
        reasons.append("executed-membership-mismatch")
    return reasons


def _coverage_provenance_reasons(
    plan: Mapping[str, object],
    coverage: Mapping[str, object],
) -> list[str]:
    unit = _find_unit(plan, coverage.get("unit_identity"))
    if unit is None:
        return []
    expected = qualification_coverage_provenance_identity(plan, unit)
    if coverage.get("provenance_identity") == expected:
        return []
    return ["provenance-linkage-mismatch"]


def qualification_coverage_provenance_identity(
    plan: Mapping[str, object],
    unit: Mapping[str, object],
) -> str:
    producer = plan.get("producer")
    implementation_identity = (
        producer.get("implementation_identity")
        if isinstance(producer, Mapping)
        else None
    )
    payload: dict[str, object] = {
        "schema": COVERAGE_PROVENANCE_SCHEMA,
        "repository_identity": plan.get("repository_identity"),
        "producer_implementation_identity": implementation_identity,
        "plan_identity": plan.get("plan_identity"),
        "classification_identity": plan.get("classification_identity"),
        "unit_identity": unit.get("unit_identity"),
        "membership_identity": unit.get("membership_identity"),
    }
    return _identity(COVERAGE_PROVENANCE_SCHEMA, payload)


def validate_external_qualification_coverage(
    plan: Mapping[str, object],
    coverage: Mapping[str, object],
) -> dict[str, object]:
    """Validate linkage and exact coverage only; never validate external PASS truth."""
    plan, plan_root_reasons = require_mapping_for_validation(
        plan, reason="invalid-qualification-plan"
    )
    coverage, coverage_root_reasons = require_mapping_for_validation(
        coverage, reason="invalid-qualification-coverage"
    )
    reasons = [
        *plan_root_reasons,
        *coverage_root_reasons,
        *_qualification_plan_reasons(plan),
        *_coverage_shape_reasons(coverage),
        *_coverage_authority_reasons(coverage),
        *_external_coverage_producer_reasons(coverage.get("producer")),
        *_coverage_plan_reasons(plan, coverage),
        *_coverage_unit_reasons(plan, coverage),
        *_coverage_provenance_reasons(plan, coverage),
    ]
    return {
        "coverage_valid": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "authority": "coverage-validation-only",
    }


def external_qualification_result(
    *,
    coverage_identity: str,
    result: str,
    producer: Mapping[str, object],
) -> dict[str, object]:
    if result not in {"pass", "fail", "error", "timeout"}:
        raise ValueError("unsupported external qualification result")
    if (
        not isinstance(coverage_identity, str)
        or not coverage_identity.startswith("sha256:")
        or len(coverage_identity) != 71
        or any(char not in "0123456789abcdef" for char in coverage_identity[7:])
    ):
        raise ValueError("coverage_identity must be sha256:<64 lowercase hex>")
    producer_name = producer.get("name")
    if not isinstance(producer_name, str) or not producer_name.strip():
        raise ValueError("external result producer requires nonblank name")
    try:
        json.dumps(producer, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "external result producer must be strict JSON-portable"
        ) from exc
    payload: dict[str, object] = {
        "schema": EXTERNAL_RESULT_SCHEMA,
        "producer": dict(producer),
        "coverage_identity": coverage_identity,
        "result": result,
        "result_authority": "external",
        "certification_authority": "external",
    }
    payload["external_result_identity"] = _identity(EXTERNAL_RESULT_SCHEMA, payload)
    return payload


def _handoff_shape_reasons(handoff: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    if handoff.get("schema") != HANDOFF_SCHEMA:
        reasons.append("unsupported-handoff-schema")
    payload = {
        key: value for key, value in handoff.items() if key != "handoff_identity"
    }
    try:
        expected = _identity(HANDOFF_SCHEMA, payload)
    except (TypeError, ValueError):
        reasons.append("handoff-not-canonical-json")
        expected = None
    if expected is None or handoff.get("handoff_identity") != expected:
        reasons.append("handoff-identity-mismatch")
    return reasons


def _handoff_provenance_reasons(handoff: Mapping[str, object]) -> list[str]:
    producer = handoff.get("producer")
    provenance = handoff.get("provenance")
    producer_identity = (
        producer.get("implementation_identity")
        if isinstance(producer, Mapping)
        else None
    )
    reasons: list[str] = []
    if not isinstance(producer_identity, str) or not producer_identity.startswith(
        "sha256:"
    ):
        reasons.append("missing-producer-implementation-identity")
    if not isinstance(provenance, Mapping):
        return [*reasons, "missing-handoff-provenance"]
    checks = (
        ("producer_implementation_identity", producer_identity),
        ("repository_identity", handoff.get("repository_identity")),
        ("membership_identity", handoff.get("membership_identity")),
        ("classification_identity", handoff.get("classification_identity")),
        (
            "classification_policy_identity",
            handoff.get("classification_policy_identity"),
        ),
        ("plan_identity", handoff.get("plan_identity")),
    )
    reasons.extend(
        f"provenance-{field}-mismatch"
        for field, expected_value in checks
        if provenance.get(field) != expected_value
    )
    return reasons


def _handoff_authority_reasons(handoff: Mapping[str, object]) -> list[str]:
    fields = ("execution_authority", "result_authority", "certification_authority")
    reasons = [
        f"{field.replace('_', '-')}-must-be-external"
        for field in fields
        if handoff.get(field) != "external"
    ]
    if handoff.get("may_regroup") is not True:
        reasons.append("may-regroup-must-be-true")
    return reasons


def _handoff_identity(handoff: Mapping[str, object]) -> str | None:
    payload = {
        key: value for key, value in handoff.items() if key != "handoff_identity"
    }
    try:
        return _identity(HANDOFF_SCHEMA, payload)
    except (TypeError, ValueError):
        return None


def _handoff_content_reasons(handoff: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    if set(handoff) != _HANDOFF_REQUIRED_FIELDS:
        reasons.append("handoff-fields-mismatch")
    reasons.extend(_producer_reasons(handoff.get("producer")))
    repository_identity = handoff.get("repository_identity")
    if not isinstance(repository_identity, str) or not _REPOSITORY_IDENTITY.fullmatch(
        repository_identity
    ):
        reasons.append("invalid-qualification-repository-identity")
    classification_identity = handoff.get("classification_identity")
    if not _valid_sha256_identity(classification_identity):
        reasons.append("invalid-qualification-classification-identity")
    if not _valid_sha256_identity(handoff.get("classification_policy_identity")):
        reasons.append("invalid-qualification-classification-policy-identity")
    if not _valid_sha256_identity(handoff.get("plan_identity")):
        reasons.append("invalid-qualification-plan-identity")
    reasons.extend(
        _handoff_unit_reasons(
            handoff,
            classification_identity=classification_identity,
        )
    )
    return reasons


def _handoff_unit_reasons(
    handoff: Mapping[str, object],
    *,
    classification_identity: object,
) -> list[str]:
    units = handoff.get("units")
    if not isinstance(units, list) or not units:
        return ["invalid-qualification-units"]

    reasons: list[str] = []
    nodeids: list[str] = []
    for unit in units:
        reasons.extend(
            _unit_reasons(unit, classification_identity=classification_identity)
        )
        if isinstance(unit, Mapping) and isinstance(unit.get("nodeids"), list):
            nodeids.extend(
                str(nodeid)
                for nodeid in unit["nodeids"]
                if isinstance(nodeid, str)
            )
    try:
        membership = node_membership_identity(nodeids)
    except ValueError:
        membership = None
    if handoff.get("membership_identity") != membership:
        reasons.append("qualification-membership-identity-mismatch")
    return reasons


def validate_native_qualification_handoff(
    handoff: Mapping[str, object],
) -> dict[str, object]:
    handoff, root_reasons = require_mapping_for_validation(
        handoff, reason="invalid-qualification-handoff"
    )
    expected = _handoff_identity(handoff)
    reasons = [
        *root_reasons,
        *_handoff_shape_reasons(handoff),
        *_handoff_provenance_reasons(handoff),
        *_handoff_authority_reasons(handoff),
        *_handoff_content_reasons(handoff),
    ]
    return {
        "valid": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "handoff_identity": expected,
        "authority": "consumer-validation-only",
    }


def _native_qualification_handoff_from_plan(
    plan: Mapping[str, object],
) -> dict[str, object]:
    """Project one immutable qualification plan into the native handoff contract."""
    payload: dict[str, object] = {
        "schema": HANDOFF_SCHEMA,
        "producer": plan["producer"],
        "repository_identity": plan["repository_identity"],
        "membership_identity": plan["membership_identity"],
        "classification_identity": plan["classification_identity"],
        "classification_policy_identity": plan["classification_policy_identity"],
        "plan_identity": plan["plan_identity"],
        "units": plan["units"],
        "provenance": {
            "producer_implementation_identity": plan["producer"][
                "implementation_identity"
            ],
            "repository_identity": plan["repository_identity"],
            "membership_identity": plan["membership_identity"],
            "classification_identity": plan["classification_identity"],
            "classification_policy_identity": plan["classification_policy_identity"],
            "plan_identity": plan["plan_identity"],
        },
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
        "may_regroup": True,
    }
    payload["handoff_identity"] = _identity(HANDOFF_SCHEMA, payload)
    return payload


def native_qualification_handoff(root: Path) -> dict[str, object]:
    root = root.resolve()
    return _native_qualification_handoff_from_plan(qualification_owner_plan(root))
