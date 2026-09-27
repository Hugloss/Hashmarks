from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from . import dependency_resolution_contract as _contract
from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin


def _changed(left: object, right: object) -> str:
    return "unchanged" if left == right else "changed"


def _producer(observation: Mapping[str, object]) -> Mapping[str, object]:
    return cast("Mapping[str, object]", observation["producer"])


def _adapter_semantics(observation: Mapping[str, object]) -> str | None:
    value = _producer(observation).get("adapter_semantics")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _adapter_axis(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> str:
    before_semantics = _adapter_semantics(before)
    after_semantics = _adapter_semantics(after)
    if before_semantics is None or after_semantics is None:
        return "unknown"
    return _changed(before_semantics, after_semantics)


def _evidence_sources(
    observation: Mapping[str, object],
) -> list[Mapping[str, object]]:
    rows = observation["evidence_sources"]
    return [row for row in cast("Sequence[object]", rows) if isinstance(row, Mapping)]


def _source_topology(observation: Mapping[str, object]) -> tuple[object, ...]:
    rows = []
    for row in _evidence_sources(observation):
        authorities = tuple(str(value) for value in row.get("authorities", ()))
        rows.append(
            (
                str(row.get("source_id") or ""),
                str(row.get("kind") or ""),
                authorities,
                str(row.get("context") or ""),
            )
        )
    return tuple(sorted(rows))


def _source_content(
    observation: Mapping[str, object],
) -> tuple[str, ...] | None:
    digests: list[str] = []
    for row in _evidence_sources(observation):
        digest = row.get("producer_digest")
        if not isinstance(digest, str) or not digest:
            return None
        digests.append(digest)
    return tuple(sorted(digests))


def _source_qualification(
    observation: Mapping[str, object],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                str(row.get("completeness") or ""),
                str(row.get("truncation") or ""),
            )
            for row in _evidence_sources(observation)
        )
    )


def _source_qualification_by_id(
    observation: Mapping[str, object],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                str(row.get("source_id") or ""),
                str(row.get("completeness") or ""),
                str(row.get("truncation") or ""),
            )
            for row in _evidence_sources(observation)
        )
    )


def _qualification_axis(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> str:
    if _source_topology(before) == _source_topology(after):
        return _changed(
            _source_qualification_by_id(before),
            _source_qualification_by_id(after),
        )
    return _changed(
        _source_qualification(before),
        _source_qualification(after),
    )


def _semantic_rows(value: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in cast("Sequence[object]", value):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                key: item
                for key, item in row.items()
                if key not in {"evidence_sources", "authority", "producer_authority"}
            }
        )
    return rows


def _producer_provenance(observation: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in _producer(observation).items()
        if key != "adapter_semantics"
    }


def _change_axes(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    before_binding: Mapping[str, object],
    after_binding: Mapping[str, object],
) -> dict[str, str]:
    definition_axis = _changed(
        before["definition_identity"],
        after["definition_identity"],
    )
    resolution_axis = (
        "not-comparable"
        if definition_axis == "changed"
        else _changed(before["resolution_identity"], after["resolution_identity"])
    )
    before_content = _source_content(before)
    after_content = _source_content(after)
    content_axis = (
        "unknown"
        if before_content is None or after_content is None
        else _changed(before_content, after_content)
    )
    return {
        "repository_identity": _changed(
            before_binding["repository_identity"],
            after_binding["repository_identity"],
        ),
        "repository_generation": _changed(
            before_binding["codemap_generation"],
            after_binding["codemap_generation"],
        ),
        "semantic_definition": definition_axis,
        "semantic_resolution": resolution_axis,
        "observation": _changed(
            before["observation_identity"],
            after["observation_identity"],
        ),
        "adapter_semantics": _adapter_axis(before, after),
        "producer_provenance": _changed(
            _producer_provenance(before),
            _producer_provenance(after),
        ),
        "repository_inputs": _changed(
            before["repository_inputs"],
            after["repository_inputs"],
        ),
        "physical_evidence_topology": _changed(
            _source_topology(before),
            _source_topology(after),
        ),
        "physical_evidence_content": content_axis,
        "evidence_qualification": _qualification_axis(before, after),
        "coverage": _changed(
            _semantic_rows(before["coverage"]),
            _semantic_rows(after["coverage"]),
        ),
        "module_ownership": _changed(
            _semantic_rows(before["module_ownership"]),
            _semantic_rows(after["module_ownership"]),
        ),
    }


class DependencyResolutionDeltaMixin:
    """Compare two explicit qualified dependency observation endpoints."""

    @staticmethod
    def dependency_resolution_delta(
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        for observation in (before, after):
            DependencyResolutionEvidenceMixin._require_qualified_dependency_observation_v3(
                observation
            )
        before_binding = cast("Mapping[str, object]", before["repository_binding"])
        after_binding = cast("Mapping[str, object]", after["repository_binding"])
        delta = DependencyResolutionEvidenceMixin._dependency_resolution_delta_v3(
            before, after
        )
        return {
            **delta,
            "schema": _contract.DELTA_SCHEMA_V3,
            "before_repository_binding": dict(before_binding),
            "after_repository_binding": dict(after_binding),
            "before_adapter_semantics": _adapter_semantics(before),
            "after_adapter_semantics": _adapter_semantics(after),
            "change_axes": _change_axes(
                before,
                after,
                before_binding=before_binding,
                after_binding=after_binding,
            ),
        }
