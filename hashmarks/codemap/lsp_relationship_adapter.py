"""Translate explicitly captured LSP responses without owning an LSP client."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.paths import normalize_relative_path

from .diagnostic_provenance import COLLECTION_STATES, diagnostic_member_claims
from .lsp_hover_capture import normalize_hover_observation
from .semantic_relationship_model import (
    CLAIM_LIMIT,
    OBSERVATION_LIMIT,
    ProducerRelationshipObservation,
    bounded_token,
    content_identity,
    direct_claim,
    portable_copy,
)
from .semantic_relationship_source import (
    RelationshipSourceResolver,
    uri_member,
    validated_position,
    validated_range,
)

CAPTURE_SCHEMA = "hashmarks.lsp-relationship-capture.v1"
_METHODS = {
    "textDocument/implementation": ("implementation", "implementationProvider"),
    "textDocument/typeDefinition": ("type_definition", "typeDefinitionProvider"),
    "textDocument/definition": ("definition", "definitionProvider"),
    "textDocument/references": ("reference", "referencesProvider"),
    "textDocument/hover": ("hover", "hoverProvider"),
    "textDocument/prepareCallHierarchy": ("prepare", "callHierarchyProvider"),
    "callHierarchy/incomingCalls": ("call", "callHierarchyProvider"),
    "callHierarchy/outgoingCalls": ("call", "callHierarchyProvider"),
}
_FIELDS = frozenset(
    {
        "schema",
        "producer",
        "configuration_identity",
        "request",
        "response",
        "partial_results",
        "capabilities",
        "position_encoding",
        "collection_state",
        "documents",
    }
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) - {
        "revision",
        "text",
        "revision_kind",
        "text_encoding",
        "provenance",
    }:
        raise ValueError("LSP document snapshot has unsupported fields")
    snapshot = dict(value)
    representation = snapshot.setdefault("revision_kind", "member-bytes")
    if representation not in ("member-bytes", "utf8-document-text"):
        raise ValueError("unsupported LSP source revision representation")
    encoding = snapshot.setdefault("text_encoding", "utf-8")
    if encoding not in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        raise ValueError("unsupported LSP source text encoding")
    text = snapshot.pop("text", None)
    if text is not None:
        if not isinstance(text, str) or representation != "utf8-document-text":
            raise ValueError(
                "captured text requires utf8-document-text revision representation"
            )
        revision = hash_bytes(text.encode("utf-8"), domain=FILE_DOMAIN).hash
        if snapshot.get("revision", revision) != revision:
            raise ValueError("LSP snapshot text contradicts its claimed revision")
        snapshot["revision"] = revision
    revision = snapshot.get("revision")
    if revision is not None and (
        not isinstance(revision, str) or not _DIGEST.fullmatch(revision)
    ):
        raise ValueError("LSP source revision must be a canonical member digest")
    return snapshot


def _documents(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or len(value) > 32:
        raise ValueError("LSP documents must contain at most 32 snapshots")
    result = {}
    for raw, snapshot in value.items():
        if not isinstance(raw, str):
            raise ValueError("LSP document paths must be strings")
        path = normalize_relative_path(raw, allow_root=False)
        if path in result:
            raise ValueError("duplicate normalized LSP document paths")
        result[path] = _snapshot(snapshot)
    diagnostic_member_claims(
        {
            "scope_paths": list(result),
            "source_revisions": {
                path: row["revision"]
                for path, row in result.items()
                if row.get("revision") is not None
            },
            "source_provenance": {
                path: row.get("provenance") for path, row in result.items()
            },
        }
    )
    return result


def _hover_request_params(params: Mapping[str, Any]) -> None:
    expected = {"textDocument", "position"}
    if not expected <= set(params) <= expected | {"workDoneToken"}:
        raise ValueError(
            "hover requires textDocument, position and optional workDoneToken"
        )
    if "workDoneToken" in params:
        token = params["workDoneToken"]
        if type(token) not in (str, int) or (
            type(token) is int and not -(2**31) <= token < 2**31
        ):
            raise ValueError(
                "hover workDoneToken must be a string or signed 32-bit integer"
            )


def _document_request_params(method: str, params: Mapping[str, Any]) -> None:
    expected = {"textDocument", "position"}
    if method == "textDocument/references":
        if set(params) != expected | {"context"}:
            raise ValueError("references require textDocument, position and context")
        context = params["context"]
        if (
            not isinstance(context, Mapping)
            or set(context) != {"includeDeclaration"}
            or type(context["includeDeclaration"]) is not bool
        ):
            raise ValueError("references includeDeclaration must be a boolean")
    elif method == "textDocument/hover":
        _hover_request_params(params)
    elif set(params) != expected:
        raise ValueError("LSP request requires textDocument and position")
    document = params["textDocument"]
    if (
        not isinstance(document, Mapping)
        or set(document) != {"uri"}
        or not isinstance(document["uri"], str)
    ):
        raise ValueError("LSP request requires an explicit document URI")
    validated_position(params["position"])


def _request(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) - {"id", "method", "params", "jsonrpc"}
        or not {"id", "method", "params"} <= set(value)
    ):
        raise ValueError("LSP capture requires request id, method and params")
    if value.get("jsonrpc", "2.0") != "2.0":
        raise ValueError("unsupported LSP JSON-RPC version")
    if (
        type(value["id"]) not in (str, int)
        or not isinstance(value["method"], str)
        or value["method"] not in _METHODS
    ):
        raise ValueError("unsupported LSP request identity or method")
    params = value["params"]
    if not isinstance(params, Mapping):
        raise ValueError("LSP request parameters must be an object")
    if value["method"] in (
        "callHierarchy/incomingCalls",
        "callHierarchy/outgoingCalls",
    ):
        if set(params) != {"item"}:
            raise ValueError("call hierarchy request requires exactly one item")
        _call_item(params["item"])
    else:
        _document_request_params(value["method"], params)
    return dict(value)


def _response(capture: Mapping[str, Any]) -> None:
    response = capture["response"]
    if (
        not isinstance(response, Mapping)
        or type(response.get("id")) is not type(capture["request"]["id"])
        or response.get("id") != capture["request"]["id"]
    ):
        raise ValueError("LSP response id does not match its captured request")
    if (
        set(response) - {"jsonrpc"} not in ({"id", "result"}, {"id", "error"})
        or response.get("jsonrpc", "2.0") != "2.0"
    ):
        raise ValueError("LSP response must contain exactly a result or an error")
    if "error" in response and capture["collection_state"] == "fresh-complete":
        raise ValueError("an LSP error cannot be a fresh-complete result")
    if "error" in response:
        error = response["error"]
        if (
            not isinstance(error, Mapping)
            or set(error) - {"code", "message", "data"}
            or type(error.get("code")) is not int
            or not isinstance(error.get("message"), str)
        ):
            raise ValueError("LSP response error requires integer code and message")


def normalize_lsp_captures(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) > OBSERVATION_LIMIT
    ):
        raise ValueError("supplied_observations must contain at most 32 LSP captures")
    captures = portable_copy(value)
    return [_normalize_capture(capture) for capture in captures]


def _normalize_capture(capture: object) -> dict[str, Any]:
    if (
        not isinstance(capture, Mapping)
        or set(capture) - _FIELDS
        or capture.get("schema") != CAPTURE_SCHEMA
    ):
        raise ValueError("unsupported LSP relationship capture schema or fields")
    required = _FIELDS - {"partial_results"}
    if not required <= set(capture):
        raise ValueError("LSP capture is missing declared provenance fields")
    result = dict(capture)
    result["capture_identity"] = content_identity(capture)
    bounded_token(result["producer"], "producer")
    bounded_token(result["configuration_identity"], "configuration_identity")
    if result["position_encoding"] not in ("utf-8", "utf-16", "utf-32"):
        raise ValueError("LSP position_encoding must be explicitly captured")
    if result["collection_state"] not in COLLECTION_STATES:
        raise ValueError("unsupported LSP collection state")
    if not isinstance(result["capabilities"], Mapping):
        raise ValueError("LSP capabilities must be an object")
    result["request"] = _request(result["request"])
    result["documents"] = _documents(result["documents"])
    _response(result)
    if result["request"]["method"] == "textDocument/hover":
        normalize_hover_observation(result)
    _locations(result)  # Reject malformed locators before repository reads.
    return result


def _location(value: object, encoding: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("LSP relationship location must be an object")
    if "targetUri" in value:
        if set(value) - {
            "targetUri",
            "targetRange",
            "targetSelectionRange",
            "originSelectionRange",
        }:
            raise ValueError("unsupported LSP LocationLink fields")
        target = validated_range(value.get("targetRange"))
        selection = validated_range(value.get("targetSelectionRange"))
        if (selection["start"]["line"], selection["start"]["character"]) < (
            target["start"]["line"],
            target["start"]["character"],
        ) or (selection["end"]["line"], selection["end"]["character"]) > (
            target["end"]["line"],
            target["end"]["character"],
        ):
            raise ValueError("LSP targetSelectionRange must be within targetRange")
        origin = value.get("originSelectionRange")
        return {
            "uri": bounded_token(value.get("targetUri"), "targetUri"),
            "range": selection,
            "target_range": target,
            "origin_range": None if origin is None else validated_range(origin),
            "position_encoding": encoding,
        }
    if set(value) != {"uri", "range"}:
        raise ValueError("LSP Location requires uri and range")
    return {
        "uri": bounded_token(value["uri"], "uri"),
        "range": validated_range(value["range"]),
        "position_encoding": encoding,
    }


def _call_item(value: object) -> dict[str, Any]:
    """Validate only protocol-owned CallHierarchyItem fields, without executing LSP."""
    if (
        not isinstance(value, Mapping)
        or not {"name", "kind", "uri", "range", "selectionRange"} <= set(value)
        or set(value)
        - {"name", "kind", "uri", "range", "selectionRange", "detail", "tags", "data"}
    ):
        raise ValueError("invalid LSP CallHierarchyItem")
    bounded_token(value["name"], "call hierarchy item name")
    bounded_token(value["uri"], "call hierarchy item URI")
    if type(value["kind"]) is not int or not 1 <= value["kind"] <= 26:
        raise ValueError("invalid LSP call hierarchy symbol kind")
    if "detail" in value and (
        not isinstance(value["detail"], str) or len(value["detail"]) > 1024
    ):
        raise ValueError("invalid LSP call hierarchy detail")
    if "tags" in value and (
        not isinstance(value["tags"], list)
        or any(type(tag) is not int for tag in value["tags"])
        or len(value["tags"]) > 16
    ):
        raise ValueError("invalid LSP call hierarchy tags")
    full = validated_range(value["range"])
    selected = validated_range(value["selectionRange"])
    if (selected["start"]["line"], selected["start"]["character"]) < (
        full["start"]["line"],
        full["start"]["character"],
    ) or (selected["end"]["line"], selected["end"]["character"]) > (
        full["end"]["line"],
        full["end"]["character"],
    ):
        raise ValueError("CallHierarchyItem selectionRange exceeds range")
    return dict(value)


def _call_location(item: object, encoding: str) -> dict[str, Any]:
    row = _call_item(item)
    return _location(
        {
            "targetUri": row["uri"],
            "targetRange": row["range"],
            "targetSelectionRange": row["selectionRange"],
        },
        encoding,
    )


def _call_rows(capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize incoming/outgoing call pairs, preserving call-site ranges."""
    method = capture["request"]["method"]
    result = capture["response"].get("result")
    batches = capture.get("partial_results", [])
    if not isinstance(batches, list) or any(
        not isinstance(batch, list) for batch in batches
    ):
        raise ValueError("call hierarchy partial results must be arrays")
    if result is not None and not isinstance(result, list):
        raise ValueError("call hierarchy result must be an array or null")
    rows = [row for batch in [*batches, result or []] for row in batch]
    if len(rows) > 512:
        raise ValueError("call hierarchy capture exceeds entry bound")
    normalized = []
    for row in rows:
        key = "from" if method == "callHierarchy/incomingCalls" else "to"
        if not isinstance(row, Mapping) or set(row) != {key, "fromRanges"}:
            raise ValueError("call hierarchy call requires endpoint and fromRanges")
        if not isinstance(row["fromRanges"], list) or len(row["fromRanges"]) > 128:
            raise ValueError("call hierarchy fromRanges must be a bounded array")
        normalized.append(
            {
                "location": _call_location(row[key], capture["position_encoding"]),
                "fromRanges": [validated_range(r) for r in row["fromRanges"]],
                "item": _call_item(row[key]),
            }
        )
    return normalized


def _locations(capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    method = capture["request"]["method"]
    if method == "textDocument/hover":
        return []  # A hover is an opaque fact, never a relationship location.
    if method in ("callHierarchy/incomingCalls", "callHierarchy/outgoingCalls"):
        return _call_rows(capture)
    batches = capture.get("partial_results", [])
    if not isinstance(batches, list) or any(
        not isinstance(batch, list) for batch in batches
    ):
        raise ValueError("LSP partial_results must be captured arrays")
    result = capture["response"].get("result")
    final = [] if result is None else result if isinstance(result, list) else [result]
    if method == "textDocument/prepareCallHierarchy":
        items = [item for batch in [*batches, final] for item in batch]
        if len(items) > 512:
            raise ValueError("call hierarchy prepare exceeds item bound")
        return [
            {
                "location": _call_location(item, capture["position_encoding"]),
                "item": _call_item(item),
            }
            for item in items
        ]
    return [
        _location(row, capture["position_encoding"])
        for batch in [*batches, final]
        for row in batch
    ]


def _query_endpoint(
    capture: Mapping[str, Any],
    target: Mapping[str, Any],
    resolver: RelationshipSourceResolver,
) -> dict[str, Any]:
    subject = f"{target['path']}::{target['qualname']}"
    params = capture["request"]["params"]
    item = params.get("item")
    if item is not None:
        query_uri = item["uri"]
        position = item["selectionRange"]["start"]
    else:
        query_uri = params["textDocument"]["uri"]
        position = params["position"]
    path = uri_member(query_uri, resolver.codemap.workspace)
    if (
        path is None
        or path != subject.split("::", 1)[0]
        or path not in capture["documents"]
    ):
        raise ValueError("LSP request must name the subject's admitted snapshot")
    if (
        not int(target["start_line"])
        <= position["line"] + 1
        <= int(target.get("end_line", target["start_line"]))
    ):
        raise ValueError("LSP request position is outside the supplied query subject")
    locator = {
        "path": path,
        "start": position,
        "end": position,
        "position_encoding": capture["position_encoding"],
    }
    resolution = resolver.candidates(
        path, locator, capture["documents"][path], name=str(target["name"])
    )
    if resolution["state"] == "unique-candidate" and (
        resolution["candidates"][0]["symbol_id"] != subject
    ):
        resolution["state"] = "unresolved"
    return {
        "key": {"namespace": capture["producer"], "supplied_subject": subject},
        "locator": locator,
        "resolution": resolution,
        "source_binding": resolver.binding(path, capture["documents"][path]),
        "subject_authority": "caller-supplied-query-subject",
    }


def _result_endpoint(
    location: Mapping[str, Any],
    capture: Mapping[str, Any],
    resolver: RelationshipSourceResolver,
) -> dict[str, Any] | None:
    path = uri_member(location["uri"], resolver.codemap.workspace)
    locator = {
        **location["range"],
        "position_encoding": location["position_encoding"],
        "path": path,
        "uri": location["uri"],
    }
    if path is None:
        return {
            "key": {
                "namespace": capture["producer"],
                "external_locator": dict(location),
            },
            "locator": locator,
            "resolution": {
                "state": "outside-repository",
                "candidates": [],
                "negative_evidence_admissible": False,
            },
        }
    if not resolver.admitted(path):
        return None
    snapshot = capture["documents"].get(path, {})
    resolution = resolver.candidates(path, locator, snapshot)
    key = {
        "namespace": capture["producer"],
        "locator": {"path": path, "range": location["range"]},
    }
    if resolution["state"] == "unique-candidate":
        key = {
            "namespace": capture["producer"],
            "repository_symbol": resolution["candidates"][0]["symbol_id"],
        }
    return {
        "key": key,
        "locator": locator,
        "resolution": resolution,
        "source_binding": resolver.binding(path, snapshot),
    }


def lsp_relationship_observation(
    capture: Mapping[str, Any],
    target: Mapping[str, Any],
    resolver: RelationshipSourceResolver,
) -> dict[str, Any]:
    query = _query_endpoint(capture, target, resolver)
    method = capture["request"]["method"]
    kind, capability = _METHODS[method]
    observation = ProducerRelationshipObservation(
        producer=capture["producer"],
        configuration_identity=capture["configuration_identity"],
        scope={
            "subject": f"{target['path']}::{target['qualname']}",
            "method": method,
            "authority": "caller-declared-request-scope",
        },
        capability={
            "declared": capture["capabilities"].get(capability),
            "captured_capabilities": dict(capture["capabilities"]),
            "authority": "producer-claimed",
            "observed_operation": method,
            "request_id": capture["request"]["id"],
            "response_error": capture["response"].get("error"),
            "partial_result_batches": len(capture.get("partial_results", [])),
        },
        collection_state=capture["collection_state"],
        capture_identity=capture["capture_identity"],
        freshness="current"
        if query["source_binding"]["state"] == "matching"
        else "unknown",
    )
    if method == "textDocument/hover":
        observation.capability["hover_observation"] = normalize_hover_observation(
            capture
        )
    locations = _locations(capture)
    unique = {content_identity(row): row for row in locations}
    prepare = method == "textDocument/prepareCallHierarchy"
    documents = capture["documents"]
    document_bindings = [
        resolver.binding(path, snapshot) for path, snapshot in sorted(documents.items())
    ]
    unadmitted_documents = sum(not resolver.admitted(path) for path in documents)
    observation.accounting = {
        "received": 0 if prepare else len(locations),
        "duplicates": 0 if prepare else len(locations) - len(unique),
        "prepare_items_received": len(locations) if prepare else 0,
        "prepare_items_retained": min(len(unique), CLAIM_LIMIT) if prepare else 0,
        "denied_or_unadmitted": 0,
        "omitted_locations": 0 if prepare else max(0, len(unique) - CLAIM_LIMIT),
        "prepare_items_omitted": max(0, len(unique) - CLAIM_LIMIT) if prepare else 0,
        "documents_received": len(documents),
        "documents_unadmitted": unadmitted_documents,
    }
    observation.truncated = len(unique) > CLAIM_LIMIT
    if prepare:
        observation.capability["prepared_candidates"] = [
            {
                "item": row["item"],
                "resolution": _result_endpoint(row["location"], capture, resolver),
                "authority": "caller-supplied-navigation-candidate-only",
            }
            for _ident, row in sorted(unique.items())[:CLAIM_LIMIT]
        ]
    for _identity, location in sorted(unique.items())[:CLAIM_LIMIT]:
        if prepare:
            continue  # Preparation produces navigation candidates, never call edges.
        endpoint = _result_endpoint(
            location["location"] if kind == "call" else location, capture, resolver
        )
        if endpoint is None:
            observation.accounting["denied_or_unadmitted"] += 1
            continue
        result_to_query = kind == "implementation" or method in (
            "textDocument/references",
            "callHierarchy/incomingCalls",
        )
        source, destination = (
            (endpoint, query) if result_to_query else (query, endpoint)
        )
        observation.claims.append(
            direct_claim(
                capture["producer"],
                kind,
                source,
                destination,
                {
                    "format": "lsp",
                    "method": method,
                    "request_id": capture["request"]["id"],
                    "direction": "result-to-query"
                    if result_to_query
                    else "query-to-result",
                    "captured_location": location,
                    "fromRanges": location.get("fromRanges", [])
                    if kind == "call"
                    else [],
                    "fromRanges_authority": "caller-supplied-call-site-ranges"
                    if kind == "call"
                    else None,
                },
            )
        )
    # Preserve every supplied snapshot.  An unadmitted path remains an
    # explicit unknown/unsupported source binding instead of disappearing
    # behind the capture identity.
    observation.source_bindings = document_bindings
    return observation.packet()
