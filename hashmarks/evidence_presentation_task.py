"""Lossless default and initial projections of producer-owned task evidence.

This owner formats supplied facts only. The canonical projection builder owns
bounds, reference escaping, counting and omission accounting.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .evidence_presentation import _Projection


def _task_owner_display_qualified(
    ownership: Mapping[str, object],
    owner_path: object,
    freshness: object,
) -> bool:
    """Respect existing producer-owned proof/freshness, without redeciding owner."""
    return (
        ownership.get("status") == "resolved"
        and ownership.get("proof_scope_complete") is True
        and ownership.get("authority") == "repository-ownership-only"
        and isinstance(owner_path, str)
        and bool(owner_path)
        and isinstance(freshness, Mapping)
        and freshness.get("state") == "current"
    )


def _task_ownership(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Project owner claims without promoting incomplete or stale evidence."""
    ownership = packet.get("ownership")
    if not isinstance(ownership, Mapping):
        return
    owner = ownership.get("owner")
    owner_path = owner.get("path") if isinstance(owner, Mapping) else None
    freshness = packet.get("freshness")
    freshness_state = (
        freshness.get("state") if isinstance(freshness, Mapping) else "unknown"
    )
    qualified = _task_owner_display_qualified(ownership, owner_path, freshness)
    ownership_context = {
        **ctx,
        "task_ownership": {
            "status": ownership.get("status"),
            "authority": ownership.get("authority"),
            "authority_proof_identity": ownership.get("authority_proof_identity"),
            "proof_scope_complete": ownership.get("proof_scope_complete"),
            "owner_path": owner_path,
            "freshness_state": freshness_state,
            "display_qualification": (
                "producer-claimed-qualified" if qualified else "unqualified"
            ),
        },
    }
    for key, family, kind, assertion in (
        (
            "owner",
            "ownership_evidence",
            "qualified_owner" if qualified else "unqualified_owner",
            "observed_fact" if qualified else "producer_claim",
        ),
        ("candidate", "ownership_evidence", "owner_candidate", "producer_claim"),
        (
            "source_evidence",
            "source",
            "owner_source_evidence" if qualified else "unqualified_owner_source",
            "observed_fact" if qualified else "producer_claim",
        ),
        ("next_read", "ownership_evidence", "discrimination_read", "producer_claim"),
    ):
        if isinstance(ownership.get(key), Mapping):
            p.field(
                ownership,
                key,
                family,
                (*ref, "ownership"),
                ownership_context,
                kind=kind,
                shape="record",
                assertion=assertion,
            )


def _task_verification(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Show producer-owned verification choices without executing them."""
    verification = packet.get("verification")
    if isinstance(verification, Mapping):
        verification_context = {
            **ctx,
            "verification_authority": verification.get("authority"),
        }
        for key, kind in (
            ("selected", "selected_verifier"),
            ("plan", "verification_plan"),
        ):
            if isinstance(verification.get(key), Mapping):
                p.field(
                    verification,
                    key,
                    "verification",
                    (*ref, "verification"),
                    verification_context,
                    kind=kind,
                    shape="record",
                    assertion="producer_claim",
                )
        relevance = verification.get("relevance")
        task_matches = (
            relevance.get("task_matches") if isinstance(relevance, Mapping) else None
        )
        if isinstance(task_matches, Mapping):
            match_context = {
                **verification_context,
                "task_match_qualification": {
                    key: deepcopy(value)
                    for key, value in task_matches.items()
                    if key != "matches"
                },
            }
            p.field(
                task_matches,
                "matches",
                "verification",
                (*ref, "verification", "relevance", "task_matches"),
                match_context,
                kind="lexical_test_term_match",
                assertion="producer_claim",
            )


def project_task(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    retrieval = packet.get("retrieval")
    if retrieval is not None:
        if not isinstance(retrieval, Mapping):
            raise ValueError("malformed task retrieval")
        retrieval_ref = (*ref, "retrieval")
        retrieval_context = {
            **ctx,
            "retrieval": {
                key: deepcopy(value)
                for key, value in retrieval.items()
                if key != "results"
            },
        }
        p.record_context(retrieval_ref, retrieval_context)
        p.field(
            retrieval, "results", "retrieval_evidence", retrieval_ref, retrieval_context
        )
    _task_ownership(p, packet, ref, ctx)
    _task_verification(p, packet, ref, ctx)
    p.field(
        packet,
        "semantic_relationships",
        "relationship",
        ref,
        ctx,
        kind="scip_semantic_discovery",
        shape="record",
        assertion="producer_claim",
    )
    for key, family in (
        ("ownership", "ownership_evidence"),
        ("supplied_observation_accounting", "qualification"),
        ("verification", "verification"),
        ("explicit_target", "ownership_evidence"),
        ("evidence_receipt", "qualification"),
        ("related", "relationship"),
    ):
        p.field(packet, key, family, ref, ctx, shape="record")
    related = packet.get("related")
    if isinstance(related, Mapping):
        p.nested(related, "resource_lifecycle", (*ref, "related"), ctx)


def compact_initial_relationships(result: dict[str, Any]) -> None:
    """Retain relationship values once, with explicit references for duplicates."""
    from hashmarks.evidence_presentation_text import (
        initial_semantic_relationship_details,
    )

    for group in result["groups"]:
        if group.get("finding_qualifiers", {}).get("kind") != "scip_semantic_discovery":
            continue
        for finding in group["findings"]:
            native = finding["details"]
            ref = finding["source_refs"][0]
            details, refs = initial_semantic_relationship_details(native)
            finding["details"] = {
                "record": details,
                "value_refs": refs,
                "value_ref_base": ref,
            }
            context = finding.get("source_context", {})
            qualification = context.get("record_qualification", {})
            if len(context) == 1 and _initial_qualification_repeated(
                qualification, native
            ):
                finding.pop("source_context")
            result["source_context"] = [
                context
                for context in result["source_context"]
                if context["source_ref"] != ref
                or not _initial_qualification_repeated(context["details"], native)
            ]


def _initial_qualification_repeated(
    qualification: Mapping[str, Any], native: Mapping[str, Any]
) -> bool:
    return all(
        key in native
        and json.dumps(value, sort_keys=True) == json.dumps(native[key], sort_keys=True)
        for key, value in qualification.items()
    )


def compact_initial_groups(groups: list[dict[str, Any]]) -> None:
    # Initial records already carry their complete display details. Avoid
    # repeating locator fields at both record and details levels.
    for group in groups:
        findings = group["findings"]
        common = {
            key: findings[0][key]
            for key in ("kind", "assertion")
            if findings
            and all(row.get(key) == findings[0].get(key) for row in findings)
        }
        group["finding_qualifiers"] = common
        for finding in group["findings"]:
            for key in list(finding):
                if key not in {
                    "kind",
                    "assertion",
                    "details",
                    "source_refs",
                    "source_context",
                }:
                    finding.pop(key)
            for key in common:
                finding.pop(key)
            if not finding.get("source_context"):
                finding.pop("source_context", None)


def compact_initial_declarations(groups: list[dict[str, Any]]) -> None:
    """Render lexical scopes once; the native packet retains the exact records."""
    from hashmarks.evidence_declaration_text import (
        declaration_common_qualifiers,
        declaration_scope_table,
    )

    for group in groups:
        if group["family"] != "retrieval_evidence":
            continue
        contexts = [
            details[family]
            for finding in group["findings"]
            if isinstance(details := finding.get("details"), dict)
            for family in (
                "class_declarations",
                "enclosing_declarations",
                "same_name_declarations",
                "direct_call_declarations",
            )
            if isinstance(details.get(family), dict)
        ]
        shared = declaration_common_qualifiers(contexts)
        if contexts:
            group["declaration_qualifiers"] = shared
            group["declaration_table"] = (
                "Scope = finding source_ref + /family; rows = scope/declarations/i; symbol prefix; extras retain absence."
            )
        for finding in group["findings"]:
            details = finding.get("details")
            if not isinstance(details, dict):
                continue
            for family in (
                "class_declarations",
                "enclosing_declarations",
                "same_name_declarations",
                "direct_call_declarations",
            ):
                context = details.get(family)
                if isinstance(context, dict):
                    # The finding's exact source_ref and this family key bind
                    # the table; repeating the full pointer adds no source fact.
                    details[family] = declaration_scope_table(context, shared=shared)


def _initial_verification_qualifier_table(
    details: list[dict[str, Any]],
) -> tuple[list[str], list[list[object]], list[dict[str, Any]]] | None:
    """Encode repeated qualifier combinations without changing any supplied value."""
    columns = ["reference_strength", "direct_reference", "indirect_reference"]
    if not all(all(key in row for key in columns) for row in details):
        return None
    keys: dict[str, int] = {}
    qualifiers: list[list[object]] = []
    rows = []
    for detail in details:
        values = [detail[key] for key in columns]
        key = json.dumps(values, sort_keys=True, ensure_ascii=False, allow_nan=False)
        index = keys.setdefault(key, len(qualifiers))
        if index == len(qualifiers):
            qualifiers.append(values)
        rows.append(
            {
                **{key: value for key, value in detail.items() if key not in columns},
                "qualifiers": index,
            }
        )
    original = {"rows": details}
    encoded = {
        "rows": rows,
        "qualifier_columns": columns,
        "qualifier_sets": qualifiers,
    }
    sizes = [
        len(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
        for value in (original, encoded)
    ]
    if sizes[1] >= sizes[0]:
        return None
    return columns, qualifiers, rows


def compact_initial_verification_qualifiers(groups: list[dict[str, Any]]) -> None:
    """Common qualifier values apply to each locator, never to omitted evidence."""
    for group in groups:
        if group["family"] != "verification" or len(group["findings"]) < 2:
            continue
        details = [finding["details"] for finding in group["findings"]]
        common = {
            key: details[0][key]
            for key in ("reference_strength", "direct_reference", "indirect_reference")
            if key in details[0]
            and all(
                key in row and json.dumps(row[key]) == json.dumps(details[0][key])
                for row in details
            )
        }
        if not common:
            table = _initial_verification_qualifier_table(details)
            if table is not None:
                columns, qualifiers, rows = table
                group["qualifier_columns"] = columns
                group["qualifier_sets"] = qualifiers
                for finding, row in zip(group["findings"], rows, strict=True):
                    finding["details"] = row
            continue
        group["locator_qualifiers"] = common
        for row in details:
            for key in common:
                row.pop(key)


def project_initial_task(
    p: _Projection, packet: Mapping[str, object], ref: tuple[object, ...]
) -> None:
    """Expose initial locators with the producer's qualifications and omissions."""
    from hashmarks.codemap.task_evidence_initial import decode_initial_collection

    p.field(
        packet,
        "semantic_relationships",
        "relationship",
        ref,
        {},
        kind="scip_semantic_discovery",
        shape="record",
        assertion="producer_claim",
    )
    ownership = packet["ownership"]
    retrieval = packet["retrieval"]
    verification = packet["verification"]
    if not all(
        isinstance(value, Mapping) for value in (ownership, retrieval, verification)
    ):
        raise ValueError("malformed initial task evidence")
    assert isinstance(ownership, Mapping)
    assert isinstance(retrieval, Mapping)
    assert isinstance(verification, Mapping)
    qualification = {
        key: ownership.get(key)
        for key in (
            "status",
            "authority",
            "proof_scope",
            "proof_scope_complete",
            "ambiguity",
        )
    }
    ambiguity = qualification.get("ambiguity")
    if isinstance(ambiguity, Mapping):
        qualification["ambiguity"] = {
            key: deepcopy(ambiguity[key])
            for key in ("ambiguous", "reason", "discrimination_question")
            if key in ambiguity
        }
        qualification["ambiguity"]["alternatives"] = [
            {
                key: alternative[key]
                for key in ("path", "qualname", "start_line", "end_line")
                if key in alternative
            }
            for alternative in ambiguity.get("alternatives", [])
        ]
    qualification["freshness"] = packet.get("freshness")
    p.add(
        "ownership_evidence",
        "initial_owner",
        ownership.get("owner"),
        (*ref, "ownership", "owner"),
        qualification,
        assertion="producer_claim",
    )
    for index, row in enumerate(retrieval.get("results", [])):
        locator = {
            key: row[key]
            for key in (
                "path",
                "symbol",
                "qualname",
                "start_line",
                "end_line",
                "class_declarations",
                "enclosing_declarations",
                "same_name_declarations",
                "direct_call_declarations",
                "supplement",
            )
            if key in row
        }
        p.add(
            "retrieval_evidence",
            "initial_source_locator",
            locator,
            (*ref, "retrieval", "results", index),
            {},
            assertion="producer_claim",
        )
    relevance = verification.get("relevance")
    if isinstance(relevance, Mapping):
        rows = relevance.get("candidates", [])
        if isinstance(relevance.get("candidates_encoding"), dict):
            rows = decode_initial_collection(rows, relevance["candidates_encoding"])
        for index, row in enumerate(rows):
            locator = {
                key: row[key]
                for key in (
                    "path",
                    "qualname",
                    "reference_strength",
                    "direct_reference",
                    "indirect_reference",
                )
                if key in row
            }
            p.add(
                "verification",
                "initial_verification_locator",
                locator,
                (*ref, "verification", "relevance", "candidates", index),
                {},
                assertion="producer_claim",
            )


def initial_evidence_text(packet: Mapping[str, object]) -> str:
    """Describe admitted initial locators; their native qualifications still govern."""
    from hashmarks.codemap.task_evidence_initial import decode_initial_collection
    from hashmarks.evidence_declaration_text import declaration_scopes_text
    from hashmarks.evidence_presentation_text import initial_semantic_relationship_text

    ownership = packet["ownership"]
    retrieval = packet["retrieval"]
    verification = packet["verification"]
    if not all(
        isinstance(value, Mapping) for value in (ownership, retrieval, verification)
    ):
        raise ValueError("malformed initial task evidence")
    assert isinstance(ownership, Mapping)
    assert isinstance(retrieval, Mapping)
    assert isinstance(verification, Mapping)
    ambiguity = ownership["ambiguity"]
    if not isinstance(ambiguity, Mapping):
        raise ValueError("malformed initial ownership ambiguity")
    freshness = json.dumps(packet["freshness"], sort_keys=True, ensure_ascii=False)
    lines = [
        f"Ownership: {ownership['status']}; freshness: {freshness} (@ /ownership, /freshness).",
        f"Ambiguity: {ambiguity.get('ambiguous', 'unknown')} (@ /ownership/ambiguity).",
        f"Owner proof scope: {ownership.get('proof_scope', 'unknown')}; complete: {ownership.get('proof_scope_complete', 'unknown')}; authority: {ownership.get('authority', 'unknown')} (@ /ownership).",
    ]
    owner = ownership.get("owner")
    if isinstance(owner, Mapping):
        owner_name = owner.get("qualname")
        owner_locator = str(owner["path"]) + (f"::{owner_name}" if owner_name else "")
        lines.append(f"Owner observation: {owner_locator} (@ /ownership/owner).")
    else:
        lines.append("Owner unresolved (@ /ownership/owner).")
    for index, row in enumerate(retrieval.get("results", [])):
        lines.append(
            f"Source candidate: {row['path']}::{row.get('symbol', row.get('qualname', ''))} ({row.get('start_line', 'unknown')}:{row.get('end_line', 'unknown')}; basis: {row.get('supplement', 'canonical-retrieval')}; @ /retrieval/results/{index})."
        )
    lines.extend(declaration_scopes_text(retrieval.get("results", [])))
    lines.extend(initial_semantic_relationship_text(packet))
    relevance = verification.get("relevance")
    if isinstance(relevance, Mapping):
        rows = relevance.get("candidates", [])
        if isinstance(relevance.get("candidates_encoding"), dict):
            rows = decode_initial_collection(rows, relevance["candidates_encoding"])
        for index, row in enumerate(rows):
            lines.append(
                f"Verification candidate: {row['path']}; reference: {row.get('reference_strength', 'unknown')}; direct: {row.get('direct_reference', 'unknown')}; indirect: {row.get('indirect_reference', 'unknown')} (@ /verification/relevance/candidates/{index})."
            )
    lines.append(
        "Qualification details remain in the native packet. Omissions: /initial_projection/omissions; omissions do not establish absence. Verification is relevance evidence; tests were not executed."
    )
    return "\n".join(lines)
