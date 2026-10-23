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

_MAX_INITIAL_INLINE_TEXT_BYTES = 2048
_NEXT_READ_TEXT_FIELDS = frozenset(
    {
        "reason",
        "role",
        "path",
        "symbol",
        "lines",
        "authority",
        "ambiguity_reason",
        "selection_basis",
        "discriminator",
        "availability_reason",
        "estimated_tokens",
        "candidate_count",
        "start_line",
        "end_line",
    }
)

_INITIAL_VERIFICATION_QUALIFIERS = (
    "reference_strength",
    "direct_reference",
    "indirect_reference",
    "verification_selection_authority",
    "edit_relationship",
    "negative_evidence_admissible",
)


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


def compact_initial_record_contexts(result: dict[str, Any]) -> None:
    """Retain exact qualifications once beside the record they qualify."""
    from hashmarks.evidence_presentation_text import (
        initial_semantic_relationship_details,
    )

    for group in result["groups"]:
        kind = group.get("finding_qualifiers", {}).get("kind")
        if kind not in {
            "scip_semantic_discovery",
            "initial_verification_locator",
            "task_source_excerpts",
        }:
            continue
        for finding in group["findings"]:
            native = finding["details"]
            ref = finding["source_refs"][0]
            if kind == "scip_semantic_discovery":
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


def _factor_source_records(
    container: dict[str, Any], key: str, qualifier_key: str
) -> None:
    """Factor only present, JSON-identical fields and keep every record in order."""
    rows = container.get(key)
    if (
        not isinstance(rows, list)
        or len(rows) < 2
        or not all(isinstance(row, dict) for row in rows)
        or qualifier_key in container
    ):
        return

    def encoded(value: object) -> bytes:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    common = {
        field: value
        for field, value in rows[0].items()
        if all(field in row and encoded(row[field]) == encoded(value) for row in rows)
    }
    if not common:
        return
    projected = [
        {field: value for field, value in row.items() if field not in common}
        for row in rows
    ]
    if len(encoded({key: projected, qualifier_key: common})) >= len(
        encoded({key: rows})
    ):
        return
    container[key] = projected
    container[qualifier_key] = common


def compact_initial_source_qualifiers(groups: list[dict[str, Any]]) -> None:
    """Shared qualifiers apply to each displayed source record, never missing rows."""
    for group in groups:
        if group["family"] != "source":
            continue
        for finding in group["findings"]:
            details = finding.get("details")
            if not isinstance(details, dict):
                continue
            anchors = details.get("line_anchors")
            if not isinstance(anchors, list):
                continue
            for anchor in anchors:
                if isinstance(anchor, dict):
                    _factor_source_records(
                        anchor, "context_excerpt", "context_excerpt_qualifiers"
                    )
            _factor_source_records(details, "line_anchors", "line_anchor_qualifiers")


def _compact_initial_field_declarations(groups: list[dict[str, Any]]) -> None:
    from hashmarks.evidence_declaration_text import field_declaration_scope

    for group in groups:
        if group["family"] != "retrieval_evidence":
            continue
        for finding in group["findings"]:
            details = finding.get("details", {})
            fields = details.get("field_declarations")
            if isinstance(fields, dict):
                details["field_declarations"] = field_declaration_scope(
                    fields, finding["source_refs"][0] + "/field_declarations"
                )


def compact_initial_declarations(groups: list[dict[str, Any]]) -> None:
    """Render lexical scopes once; the native packet retains the exact records."""
    from hashmarks.evidence_declaration_text import (
        declaration_common_qualifiers,
        declaration_scope_table,
    )

    _compact_initial_field_declarations(groups)
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
    columns = [
        key
        for key in _INITIAL_VERIFICATION_QUALIFIERS
        if all(key in row for row in details)
    ]
    if not columns:
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
            for key in _INITIAL_VERIFICATION_QUALIFIERS
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


def _initial_verification_locator(row: Mapping[str, Any]) -> dict[str, Any]:
    """Retain supplied test identity and qualifiers without resolving uncertainty."""
    return {
        key: row[key]
        for key in (
            "path",
            "qualname",
            "test_symbol",
            "test_revision",
            "test_declarations",
            *_INITIAL_VERIFICATION_QUALIFIERS,
        )
        if key in row
    }


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
    owner = ownership.get("owner")
    owner_path = owner.get("path") if isinstance(owner, Mapping) else None
    qualification["display_qualification"] = (
        "producer-claimed-qualified"
        if _task_owner_display_qualified(ownership, owner_path, packet.get("freshness"))
        else "unqualified"
    )
    p.add(
        "ownership_evidence",
        "initial_owner",
        ownership.get("owner"),
        (*ref, "ownership", "owner"),
        qualification,
        assertion="producer_claim",
    )
    next_read = ownership.get("next_read")
    if isinstance(next_read, Mapping):
        # Owner display qualification belongs to the owner observation, not
        # to an independent read suggestion. Its own native authority/reason
        # travels in details, with the source JSON pointer and producer claim.
        p.add(
            "ownership_evidence",
            "initial_discrimination_read",
            next_read,
            (*ref, "ownership", "next_read"),
            {},
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
                "field_declarations",
                "source_selection",
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
        _project_initial_source_context(p, row, (*ref, "retrieval", "results", index))
    relevance = verification.get("relevance")
    if isinstance(relevance, Mapping):
        rows = relevance.get("candidates", [])
        if isinstance(relevance.get("candidates_encoding"), dict):
            rows = decode_initial_collection(rows, relevance["candidates_encoding"])
        for index, row in enumerate(rows):
            p.add(
                "verification",
                "initial_verification_locator",
                _initial_verification_locator(row),
                (*ref, "verification", "relevance", "candidates", index),
                {},
                assertion="producer_claim",
            )


def _initial_field_declarations_text(rows: list[dict[str, Any]]) -> list[str]:
    from hashmarks.evidence_declaration_text import field_declaration_scope

    return [
        "Declared field syntax @ /retrieval/results/"
        + str(index)
        + "/field_declarations: "
        + json.dumps(
            field_declaration_scope(
                row["field_declarations"],
                f"/retrieval/results/{index}/field_declarations",
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        for index, row in enumerate(rows)
        if isinstance(row.get("field_declarations"), Mapping)
    ]


def _source_context_view(
    observation: Mapping[str, object], ref: str
) -> dict[str, object]:
    """Display exact anchors and qualification; reference remaining native metadata."""
    return {
        "metadata_ref": ref,
        **{
            key: observation[key]
            for key in (
                "member",
                "freshness",
                "availability",
                "completeness",
                "truncation",
                "requested_lines",
                "line_anchors",
                "line_coverage",
                "negative_evidence",
                "authority",
                "execution_effect",
            )
            if key in observation
        },
    }


def _project_initial_source_context(
    p: _Projection, row: Mapping[str, object], ref: tuple[object, ...]
) -> None:
    observation = row.get("source_observation")
    if isinstance(observation, Mapping):
        source_ref = (*ref, "source_observation")
        pointer = "/" + "/".join(
            str(part).replace("~", "~0").replace("/", "~1") for part in source_ref
        )
        p.add(
            "source",
            "task_source_excerpts",
            _source_context_view(observation, pointer),
            source_ref,
            {},
            assertion="observed_fact",
        )


def _initial_source_context_text(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for index, row in enumerate(rows):
        observation = row.get("source_observation")
        if isinstance(observation, Mapping):
            ref = f"/retrieval/results/{index}/source_observation"
            lines.append(
                f"Source observation @ {ref}: "
                + json.dumps(
                    _source_context_view(observation, ref),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        selection = row.get("source_selection")
        if isinstance(selection, Mapping):
            lines.append(
                f"Source selection @ /retrieval/results/{index}/source_selection: "
                + json.dumps(selection, sort_keys=True, separators=(",", ":"))
            )
    return lines


def _initial_ambiguity_text(ambiguity: Mapping[str, Any]) -> list[str]:
    """Display retained producer alternatives without expanding their scope."""
    lines = []
    for key, label in (
        ("reason", "Ambiguity reason"),
        ("discrimination_question", "Discrimination question"),
    ):
        if ambiguity.get(key) is not None:
            # Source-derived ambiguity text is untrusted presentation data.
            # Keep ordinary one-line values unchanged, but escape control
            # characters so a producer string cannot forge extra evidence
            # lines. Native source remains complete behind the exact pointer.
            rendered = str(ambiguity[key])
            if not rendered.isprintable():
                rendered = json.dumps(rendered, ensure_ascii=False)
            if len(rendered.encode("utf-8")) > _MAX_INITIAL_INLINE_TEXT_BYTES:
                rendered = "native-details-only;inline-budget-exceeded"
            lines.append(f"{label}: {rendered} (@ /ownership/ambiguity/{key}).")
    for index, alternative in enumerate(ambiguity.get("alternatives", [])):
        locator = {
            key: alternative[key]
            for key in ("path", "symbol", "qualname", "start_line", "end_line")
            if key in alternative
        }
        lines.append(
            "Owner alternative: "
            + json.dumps(locator, ensure_ascii=False, separators=(",", ":"))
            + f" (@ /ownership/ambiguity/alternatives/{index})."
        )
    return lines


def _initial_next_read_text(ownership: Mapping[str, object]) -> list[str]:
    """Display an existing producer nomination, never choose an action."""
    next_read = ownership.get("next_read")
    if not isinstance(next_read, Mapping):
        return []
    # Only known locator/reason fields belong in the bounded first-response
    # text. The native initial packet still carries every producer field.
    displayed = {
        key: value for key, value in next_read.items() if key in _NEXT_READ_TEXT_FIELDS
    }
    payload = json.dumps(
        displayed, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    omitted = len(next_read) - len(displayed)
    if len(payload.encode("utf-8")) > _MAX_INITIAL_INLINE_TEXT_BYTES:
        payload = '{"display":"native-details-only;inline-budget-exceeded"}'
        omitted = len(next_read)
    return [
        "Producer next-read candidate: "
        + payload
        + f"; omitted fields: {omitted} (full details @ /ownership/next_read)"
        + " (@ /ownership/next_read; repository evidence only, not an execution instruction)."
    ]


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
    # Put the exact, explicitly qualified owner observation first, before
    # candidate and verification details. This only reorders existing facts;
    # the producer still owns the resolution, freshness and ambiguity.
    lines: list[str] = []
    owner = ownership.get("owner")
    if isinstance(owner, Mapping):
        owner_name = owner.get("qualname")
        owner_locator = str(owner["path"]) + (f"::{owner_name}" if owner_name else "")
        qualification = (
            "producer-claimed-qualified"
            if _task_owner_display_qualified(
                ownership, owner.get("path"), packet.get("freshness")
            )
            else "unqualified"
        )
        lines.append(
            f"Owner observation: {owner_locator}; qualification: {qualification} "
            "(@ /ownership/owner)."
        )
    else:
        lines.append("Owner unresolved (@ /ownership/owner).")
    lines.extend(
        (
            f"Ownership: {ownership['status']}; freshness: {freshness} (@ /ownership, /freshness).",
            f"Ambiguity: {ambiguity.get('ambiguous', 'unknown')} (@ /ownership/ambiguity).",
            f"Owner proof scope: {ownership.get('proof_scope', 'unknown')}; complete: {ownership.get('proof_scope_complete', 'unknown')}; authority: {ownership.get('authority', 'unknown')} (@ /ownership).",
        )
    )
    lines.extend(
        (*_initial_ambiguity_text(ambiguity), *_initial_next_read_text(ownership))
    )
    for index, row in enumerate(retrieval.get("results", [])):
        lines.append(
            f"Source candidate: {row['path']}::{row.get('symbol', row.get('qualname', ''))} ({row.get('start_line', 'unknown')}:{row.get('end_line', 'unknown')}; basis: {row.get('supplement', 'canonical-retrieval')}; @ /retrieval/results/{index})."
        )
    lines.extend(declaration_scopes_text(retrieval.get("results", [])))
    lines.extend(_initial_field_declarations_text(retrieval.get("results", [])))
    lines.extend(_initial_source_context_text(retrieval.get("results", [])))
    lines.extend(initial_semantic_relationship_text(packet))
    relevance = verification.get("relevance")
    if isinstance(relevance, Mapping):
        rows = relevance.get("candidates", [])
        if isinstance(relevance.get("candidates_encoding"), dict):
            rows = decode_initial_collection(rows, relevance["candidates_encoding"])
        for index, row in enumerate(rows):
            locator = json.dumps(
                _initial_verification_locator(row),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            lines.append(
                f"Verification candidate: {locator} (@ /verification/relevance/candidates/{index})."
            )
    lines.append(
        "Qualification details remain in the native packet. Omissions: /initial_projection/omissions; omissions do not establish absence. Verification is relevance evidence; tests were not executed."
    )
    return "\n".join(lines)
