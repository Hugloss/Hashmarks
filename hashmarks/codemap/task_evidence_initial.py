"""Pure initial disclosure of an already observed task packet.

This profile bounds presentation, never the producer's ownership or reference
decision. The full packet identity and an omission ledger permit comparison
with a later full observation; they are not durable replay state.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from hashmarks.digest import hash_bytes
from hashmarks.operation_contract import operation_schema, validate_operation_response


def initial_packet_identity(packet: dict[str, Any]) -> str:
    """Bind the decoded semantic view, independent of its wire encoding."""
    semantic = {
        key: value for key, value in packet.items() if key != "evidence_packet_identity"
    }
    encoded = json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    domain = operation_schema("task_evidence", "initial").encode("utf-8") + b"\0"
    return "sha256:" + hash_bytes(encoded, domain=domain).hash


def _collect_strings(value: Any, strings: set[str]) -> None:
    if isinstance(value, str):
        strings.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("initial object keys must be strings")
            strings.add(key)
            _collect_strings(item, strings)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, strings)


def _encode_strings(value: Any, indices: dict[str, str]) -> Any:
    if isinstance(value, str):
        return indices[value]
    if isinstance(value, dict):
        return {
            indices[key]: _encode_strings(item, indices) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_encode_strings(item, indices) for item in value]
    return value


def encode_initial_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Losslessly serialize a semantic initial packet using a local string table."""
    headers = {
        key: packet[key]
        for key in ("schema", "source_evidence_identity", "evidence_packet_identity")
    }
    data = {key: value for key, value in packet.items() if key not in headers}
    strings: set[str] = set()

    _collect_strings(data, strings)
    ordered = sorted(strings)
    indices = {value: str(index) for index, value in enumerate(ordered)}
    table = []
    previous = ""
    for value in ordered:
        prefix = 0
        while (
            prefix < min(len(previous), len(value))
            and previous[prefix] == value[prefix]
        ):
            prefix += 1
        table.append([prefix, value[prefix:]])
        previous = value

    return {
        **headers,
        "encoding": {"kind": "json-string-table.v1", "strings": table},
        "data": _encode_strings(data, indices),
    }


def _decode_string_table(encoding: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    previous = ""
    for row in encoding["strings"]:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or type(row[0]) is not int
            or not isinstance(row[1], str)
            or not 0 <= row[0] <= len(previous)
        ):
            raise ValueError("invalid initial string table row")
        value = previous[: row[0]] + row[1]
        if strings and value <= previous:
            raise ValueError("initial string table must be distinct and sorted")
        strings.append(value)
        previous = value

    return strings


def _decode_strings(encoding: dict[str, Any], data: Any) -> Any:
    strings = _decode_string_table(encoding)

    def string(index: str) -> str:
        if (
            not index.isascii()
            or not index.isdecimal()
            or (len(index) > 1 and index[0] == "0")
            or int(index) >= len(strings)
        ):
            raise ValueError("invalid initial string reference")
        return strings[int(index)]

    def decode(value: Any) -> Any:
        if isinstance(value, str):
            return string(value)
        if isinstance(value, dict):
            return {string(key): decode(item) for key, item in value.items()}
        if isinstance(value, list):
            return [decode(item) for item in value]
        if value is None or type(value) in (bool, int, float):
            return value
        raise ValueError("invalid initial JSON value")

    return decode(data)


def decode_initial_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Resolve wire references without conflating numeric strings and numbers."""
    if packet.get("schema") != operation_schema("task_evidence", "initial"):
        raise ValueError("unsupported initial packet schema")
    if set(packet) != {
        "schema",
        "source_evidence_identity",
        "evidence_packet_identity",
        "encoding",
        "data",
    }:
        raise ValueError("invalid initial packet fields")
    encoding = packet["encoding"]
    if (
        not isinstance(encoding, dict)
        or set(encoding) != {"kind", "strings"}
        or encoding["kind"] != "json-string-table.v1"
        or not isinstance(encoding["strings"], list)
    ):
        raise ValueError("invalid initial string table")
    data = _decode_strings(encoding, packet["data"])
    if not isinstance(data, dict) or set(data) & {
        "schema",
        "source_evidence_identity",
        "evidence_packet_identity",
    }:
        raise ValueError("invalid initial semantic data")
    result = {
        **{
            key: packet[key]
            for key in (
                "schema",
                "source_evidence_identity",
                "evidence_packet_identity",
            )
        },
        **data,
    }
    if initial_packet_identity(result) != result["evidence_packet_identity"]:
        raise ValueError("initial semantic identity differs from decoded packet")
    return result


_LOCATOR_OMISSIONS = (
    "canonical_rank",
    "canonical_score",
    "name",
    "signature",
    "namespace_overlap",
    "namespace_terms",
    "task_anchor_count",
    "task_anchor_terms",
    "runner_available",
)


def _locator(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    omitted = set(_LOCATOR_OMISSIONS)
    if not value.get("qualname") and not value.get("symbol"):
        omitted.remove("name")
    return {key: item for key, item in value.items() if key not in omitted}


def _encode_rows(container: dict[str, Any], key: str, columns: list[str]) -> None:
    rows = container.get(key)
    if not isinstance(rows, list):
        return
    if not all(isinstance(row, dict) and set(row) == set(columns) for row in rows):
        return
    container[key + "_encoding"] = {"kind": "columns-rows.v1", "columns": columns}
    container[key] = [[row[column] for column in columns] for row in rows]


def _encode_task_matches(relevance: dict[str, Any]) -> None:
    matches = relevance.get("task_matches")
    if isinstance(matches, dict):
        _encode_rows(
            matches, "matches", ["path", "matched_term_count", "evidence_visibility"]
        )


def _encode_candidate_rows(relevance: dict[str, Any]) -> None:
    rows = relevance.get("candidates")
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        return
    columns = sorted(set.intersection(*(set(row) for row in rows)))
    if not columns:
        return
    relevance["candidates_encoding"] = {
        "kind": "columns-rows-with-extras.v1",
        "columns": columns,
    }
    relevance["candidates"] = [
        [
            *[row[column] for column in columns],
            {key: value for key, value in row.items() if key not in columns},
        ]
        for row in rows
    ]


def decode_initial_collection(
    rows: Any, encoding: dict[str, Any]
) -> list[dict[str, Any]]:
    """Read the explicit lossless table contract without guessing missing fields."""
    columns = encoding.get("columns")
    kind = encoding.get("kind")
    if (
        kind not in {"columns-rows.v1", "columns-rows-with-extras.v1"}
        or not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        or len(set(columns)) != len(columns)
        or not isinstance(rows, list)
    ):
        raise ValueError("invalid initial collection encoding")
    decoded = []
    extras = kind == "columns-rows-with-extras.v1"
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns) + int(extras):
            raise ValueError("initial collection row differs from declared columns")
        record = dict(zip(columns, row[: len(columns)], strict=True))
        if extras:
            if not isinstance(row[-1], dict) or set(row[-1]) & set(columns):
                raise ValueError("initial collection extras overwrite declared fields")
            record.update(row[-1])
        decoded.append(record)
    return decoded


def _encode_class_declarations(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        declarations = row.get("class_declarations")
        if isinstance(declarations, dict):
            _encode_rows(
                declarations,
                "declarations",
                ["path", "symbol", "start_line", "end_line"],
            )


def _project_verification(
    verification: dict[str, Any], omissions: dict[str, Any]
) -> None:
    verification["selected"] = _locator(verification.get("selected"))
    relevance = verification.get("relevance")
    if isinstance(relevance, dict):
        _encode_task_matches(relevance)
        relevance["selected"] = _locator(relevance.get("selected"))
        candidates = relevance.get("candidates", [])
        # A selected verifier is not a completeness claim. Preserve every
        # already-bounded alternative rather than silently dropping the test
        # that answers the caller's question. Locators retain relationship and
        # freshness qualifiers; only declared display fields are omitted.
        projected = candidates
        relevance["candidates"] = [_locator(row) for row in projected]
        _encode_candidate_rows(relevance)
        omissions["collections"]["/verification/relevance/candidates"] = {
            "observed_in_source_packet": len(candidates),
            "returned": len(projected),
            "omitted": len(candidates) - len(projected),
        }


def initial_task_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    """Project existing facts, retaining qualifiers and accounting for detail loss."""
    validate_operation_response("task_evidence", packet)
    result = deepcopy(packet)
    result["schema"] = operation_schema("task_evidence", "initial")
    result["source_evidence_identity"] = result.pop("evidence_packet_identity")
    omissions: dict[str, Any] = {
        "locator_fields": list(_LOCATOR_OMISSIONS),
        "locator_scopes": [
            "/ownership/owner",
            "/ownership/candidate",
            "/ownership/ambiguity/alternatives/*",
            "/verification/selected",
            "/verification/relevance/selected",
            "/verification/relevance/candidates/*",
        ],
        "sections": [],
        "collections": {},
    }
    ownership = result["ownership"]
    for key in ("owner", "candidate"):
        ownership[key] = _locator(ownership.get(key))
    ambiguity = ownership.get("ambiguity")
    if isinstance(ambiguity, dict) and isinstance(ambiguity.get("alternatives"), list):
        ambiguity["alternatives"] = [_locator(row) for row in ambiguity["alternatives"]]
    source = ownership.get("source_evidence")
    if isinstance(source, dict) and "content" in source:
        source.pop("content")
        omissions["sections"].append("/ownership/source_evidence/content")
    retrieval = result["retrieval"]
    rows = retrieval["results"]
    # Preserve the canonical first three and already admitted declaration
    # supplements. No authority or retrieval decision is made by this profile.
    retained = rows[:3] + [row for row in rows[3:] if row.get("supplement")][:2]
    owner = ownership.get("owner")
    if isinstance(owner, dict):
        owner_row = next(
            (row for row in rows if row.get("path") == owner.get("path")), None
        )
        if owner_row is not None and owner_row not in retained:
            retained.append(owner_row)
    retrieval["results"] = retained
    _encode_class_declarations(retained)
    omissions["collections"]["/retrieval/results"] = {
        "observed_in_source_packet": len(rows),
        "returned": len(retained),
        "omitted": len(rows) - len(retained),
    }
    _project_verification(result["verification"], omissions)
    if "related" in result:
        result.pop("related")
        omissions["sections"].append("/related")
    result["initial_projection"] = {
        "authority": "projection-only",
        "omissions": omissions,
        "expansion": {
            "operation": "task_evidence",
            "result_mode": "default",
            "identity_check": "compare-full-packet-identity; changed source may differ",
        },
        "negative_evidence_from_omissions": "not-admissible",
    }
    return result
