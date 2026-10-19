"""Portable supplied verification membership; native collection remains external."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TypedDict

from .codemap.repository_observation import evidence_identity
from .operation_contract import operation_schema
from .paths import normalize_relative_path
from .verification_selection import verification_member, verification_membership

COLLECTION_REPORT_SCHEMA = "hashmarks.verification-membership-report.v1"
MEMBERSHIP_OBSERVATION_SCHEMA = operation_schema("verification_membership")
EMPTY_MEMBERSHIP_SCHEMA = "hashmarks.verification-empty-membership.v1"
MAX_COLLECTION_MEMBERS = 10_000
MAX_COLLECTION_INPUTS = 256
MAX_COLLECTION_REPORT_BYTES = 1_048_576
MAX_MEMBERSHIP_OBSERVATION_BYTES = 4_194_304
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CollectionReport(TypedDict):
    schema: str
    selection_kind: str
    producer: dict[str, object]
    provenance: dict[str, object]
    scope: dict[str, object]
    status: str
    completeness: str
    truncation: str
    members: list[dict[str, object]] | None
    inputs: list[dict[str, object]]


def portable_value(value: object, *, label: str, max_bytes: int) -> object:
    """Detach a bounded strict-JSON value from mutable caller objects."""
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} must be strict JSON-portable") from exc
    if len(raw.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} encoded bytes")
    return json.loads(raw)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _metadata(value: object, label: str) -> dict[str, object]:
    return _object(portable_value(value, label=label, max_bytes=8192), label)


def _choice(value: object, choices: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{label} must be one of {', '.join(sorted(choices))}")
    return value


def _path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("collection input path must be a string")
    return normalize_relative_path(value, allow_root=False)


def _members(value: object) -> list[dict[str, object]] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > MAX_COLLECTION_MEMBERS:
        raise ValueError(
            f"members must be null or an array of at most {MAX_COLLECTION_MEMBERS} rows"
        )
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        raw = _object(item, "verification member")
        if set(raw) - {"path", "test_symbol"}:
            raise ValueError("verification member fields must be path and test_symbol")
        symbol = raw.get("test_symbol")
        if symbol is not None and (not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError("test_symbol must be a nonblank string or null")
        member = verification_member(_path(raw.get("path")), test_symbol=symbol)
        identity = str(member["member_id"])
        if identity in seen:
            raise ValueError("duplicate verification member")
        seen.add(identity)
        rows.append({"path": member["path"], "test_symbol": member["test_symbol"]})
    return sorted(
        rows, key=lambda row: (str(row["path"]), str(row["test_symbol"] or ""))
    )


def _inputs(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > MAX_COLLECTION_INPUTS:
        raise ValueError(
            f"inputs must be an array of at most {MAX_COLLECTION_INPUTS} rows"
        )
    rows: dict[str, dict[str, object]] = {}
    for item in value:
        raw = _object(item, "collection input")
        if set(raw) - {"path", "member_revision"}:
            raise ValueError("collection input fields must be path and member_revision")
        path = _path(raw.get("path"))
        revision = raw.get("member_revision")
        if revision is not None and (
            not isinstance(revision, str) or not _HEX64.fullmatch(revision)
        ):
            raise ValueError(
                "member_revision must be a canonical 64-character Hashmarks member revision or null"
            )
        if path in rows:
            raise ValueError("duplicate collection input path")
        rows[path] = {"path": path, "member_revision": revision}
    return [rows[path] for path in sorted(rows)]


def _collection_coverage(report: CollectionReport) -> None:
    if report["completeness"] == "complete":
        if report["status"] != "succeeded" or report["truncation"] != "complete":
            raise ValueError(
                "complete collection requires claimed success and complete truncation"
            )
        if not report["scope"]:
            raise ValueError("complete collection requires an explicit claimed scope")
    if report["members"] is None and report["status"] == "succeeded":
        raise ValueError(
            "claimed successful collection requires a member array, possibly empty"
        )


def normalize_collection_report(value: object) -> CollectionReport:
    """Validate claims without attesting their producer, scope, or completeness."""
    raw = _object(
        portable_value(
            value, label="collection report", max_bytes=MAX_COLLECTION_REPORT_BYTES
        ),
        "collection report",
    )
    expected = {
        "schema",
        "selection_kind",
        "producer",
        "provenance",
        "scope",
        "status",
        "completeness",
        "truncation",
        "members",
        "inputs",
    }
    if set(raw) != expected or raw["schema"] != COLLECTION_REPORT_SCHEMA:
        raise ValueError(
            f"collection report requires the exact {COLLECTION_REPORT_SCHEMA} fields"
        )
    report = CollectionReport(
        schema=COLLECTION_REPORT_SCHEMA,
        selection_kind=_choice(
            raw["selection_kind"],
            {"native-collected", "caller-selected"},
            "selection_kind",
        ),
        producer=_metadata(raw["producer"], "producer"),
        provenance=_metadata(raw["provenance"], "provenance"),
        scope=_metadata(raw["scope"], "scope"),
        status=_choice(raw["status"], {"succeeded", "failed", "unknown"}, "status"),
        completeness=_choice(
            raw["completeness"], {"complete", "incomplete", "unknown"}, "completeness"
        ),
        truncation=_choice(
            raw["truncation"], {"complete", "truncated", "unknown"}, "truncation"
        ),
        members=_members(raw["members"]),
        inputs=_inputs(raw["inputs"]),
    )
    if not report["producer"]:
        raise ValueError("producer must identify the claimed membership producer")
    _collection_coverage(report)
    collection_inputs(report)
    return report


def collection_inputs(report: CollectionReport) -> list[dict[str, object]]:
    """Every selected path is observed, even when no revision was supplied."""
    rows = {str(row["path"]): dict(row) for row in report["inputs"]}
    for member in report["members"] or []:
        path = str(member["path"])
        rows.setdefault(path, {"path": path, "member_revision": None})
    if len(rows) > MAX_COLLECTION_INPUTS:
        raise ValueError(
            f"selected paths and inputs exceed {MAX_COLLECTION_INPUTS} unique paths"
        )
    return [rows[path] for path in sorted(rows)]


def collection_membership(report: CollectionReport) -> dict[str, object] | None:
    members = report["members"]
    if members is None:
        return None
    if members:
        return verification_membership(members)
    payload: dict[str, object] = {"schema": EMPTY_MEMBERSHIP_SCHEMA, "members": []}
    return {
        **payload,
        "member_count": 0,
        "membership_identity": evidence_identity(EMPTY_MEMBERSHIP_SCHEMA, payload),
    }


def collection_bundle(report: CollectionReport) -> dict[str, object]:
    anchors: list[dict[str, object]] = []
    for row in collection_inputs(report):
        anchor = {
            "anchor_id": evidence_identity(
                "hashmarks.verification-input.v1", {"path": row["path"]}
            ),
            "path": row["path"],
            "metadata": {},
        }
        if row["member_revision"] is not None:
            anchor["member_revision"] = row["member_revision"]
        anchors.append(anchor)
    return {
        "bundle_id": evidence_identity(COLLECTION_REPORT_SCHEMA, report),
        "producer": report["producer"],
        "provenance": report["provenance"],
        "scope": report["scope"],
        "completeness": report["completeness"],
        "truncation": report["truncation"],
        "anchors": anchors,
    }
