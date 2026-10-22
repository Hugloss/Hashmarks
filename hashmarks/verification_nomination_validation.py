"""Strict structural replay of Hashmarks verification nomination evidence.

This validates a transported packet's registered shape and domain-separated
content identity. It deliberately does not inspect a live repository, decide
which tests to run, authenticate a producer, or grant execution authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, TypedDict

from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{64}\Z")

_AVAILABLE_FIELDS = frozenset(
    {
        "schema",
        "available",
        "verification_target",
        "source_member_revision",
        "supporting_source_members",
        "scope",
        "runner_evidence",
        "source_evidence",
        "confidence",
        "authority",
        "execution_authority",
        "nomination_identity",
    }
)
_UNAVAILABLE_FIELDS = frozenset(
    {
        "schema",
        "available",
        "path",
        "reason",
        "authority",
        "execution_authority",
        "nomination_identity",
    }
)
_SCOPES = frozenset({"test-node", "test-file", "go-package", "typescript-project"})


class VerificationNominationValidation(TypedDict):
    valid: bool
    reasons: list[str]
    nomination_identity: str | None
    authority: Literal["content-integrity-only"]
    repository_binding: Literal["not-checked"]
    producer_authenticity: Literal["not-checked"]
    execution_authority: Literal["external"]


def _record(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{label}-not-an-object")
    return value


def _keys(record: Mapping[str, object], keys: frozenset[str], label: str) -> None:
    if set(record) != keys:
        raise ValueError(f"{label}-fields-mismatch")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}-not-nonblank")
    return value


def _path(value: object, label: str) -> str:
    path = _text(value, label)
    try:
        normalized = normalize_relative_path(path, allow_root=False)
    except ValueError as exc:
        raise ValueError(f"{label}-invalid-path") from exc
    if path != normalized:
        raise ValueError(f"{label}-not-canonical")
    return path


def _revision(value: object) -> str:
    if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
        raise ValueError("invalid-source-member-revision")
    return value


def _member_state(
    row: dict[str, object],
    path: str,
    *,
    is_test: bool,
    target: str,
    revision: str,
) -> None:
    state = row.get("state")
    if state == "known-present":
        _keys(
            row, frozenset({"path", "state", "member_revision"}), "present-member"
        )
        observed = _revision(row.get("member_revision"))
        if is_test and (path != target or observed != revision):
            raise ValueError("test-member-revision-mismatch")
    elif state == "known-absent":
        _keys(row, frozenset({"path", "state"}), "absent-member")
        if is_test:
            raise ValueError("test-member-not-present")
    else:
        raise ValueError("unsupported-source-member-state")


def _member_ledger(value: object, target: str, revision: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("invalid-supporting-source-members")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        row = _record(raw, "source-member")
        path = _path(row.get("path"), "source-member-path")
        if path in seen:
            raise ValueError("duplicate-source-member")
        seen.add(path)
        _member_state(
            row, path, is_test=index == 0, target=target, revision=revision
        )
    if value[0]["path"] != target:
        raise ValueError("test-member-not-first")

def _available(record: dict[str, object]) -> None:
    _keys(record, _AVAILABLE_FIELDS, "available-nomination")
    target = _record(record.get("verification_target"), "verification-target")
    _keys(target, frozenset({"path", "test_symbol"}), "verification-target")
    path = _path(target.get("path"), "verification-target-path")
    symbol = target["test_symbol"]
    if symbol is not None and (
        not isinstance(symbol, str) or not symbol.startswith("test_")
    ):
        raise ValueError("invalid-test-symbol")
    if record.get("scope") not in _SCOPES:
        raise ValueError("invalid-verification-scope")
    for name in ("runner_evidence", "source_evidence", "confidence"):
        _text(record.get(name), name)
    revision = _revision(record.get("source_member_revision"))
    _member_ledger(record.get("supporting_source_members"), path, revision)


def _unavailable(record: dict[str, object]) -> None:
    _keys(record, _UNAVAILABLE_FIELDS, "unavailable-nomination")
    _path(record.get("path"), "unavailable-path")
    _text(record.get("reason"), "unavailable-reason")


def _validate_record(value: object) -> str:
    record = _record(value, "nomination")
    schema = operation_schema("verification_nomination")
    if record.get("schema") != schema:
        raise ValueError("nomination-schema-mismatch")
    if record.get("authority") != "repository-evidence-only":
        raise ValueError("nomination-authority-mismatch")
    if record.get("execution_authority") != "external":
        raise ValueError("execution-authority-mismatch")
    available = record.get("available")
    if type(available) is not bool:
        raise ValueError("nomination-availability-not-boolean")
    if available:
        _available(record)
    else:
        _unavailable(record)
    identity = record.get("nomination_identity")
    if not isinstance(identity, str) or _SHA256.fullmatch(identity) is None:
        raise ValueError("invalid-nomination-identity")
    payload = {
        key: item for key, item in record.items() if key != "nomination_identity"
    }
    if evidence_identity(schema, payload) != identity:
        raise ValueError("nomination-identity-mismatch")
    return identity


def validate_verification_nomination(value: object) -> VerificationNominationValidation:
    """Check transported structure and digest, not source currency or authenticity."""
    identity: str | None = None
    reasons: list[str] = []
    try:
        identity = _validate_record(value)
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    return {
        "valid": not reasons,
        "reasons": reasons,
        "nomination_identity": identity if not reasons else None,
        "authority": "content-integrity-only",
        "repository_binding": "not-checked",
        "producer_authenticity": "not-checked",
        "execution_authority": "external",
    }
