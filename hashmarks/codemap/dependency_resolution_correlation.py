from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, cast

from . import dependency_resolution_contract as _contract
from .dependency_resolution_contract import normalized_text as _text
from .dependency_resolution_contract import object_rows as _objects

if TYPE_CHECKING:
    from .engine import CodeMap


def _ownership_summary(
    matches: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    owners = sorted(
        {
            str(owner)
            for row in matches
            for owner in cast("Sequence[object]", row.get("owners", ()))
            if owner
        }
    )
    states = [row.get("completeness") for row in matches]
    completeness = (
        "complete"
        if states and all(state == "complete" for state in states)
        else "incomplete"
        if "incomplete" in states
        else "unknown"
    )
    return {
        "distribution_state": (
            "resolved-unique"
            if len(owners) == 1
            else "resolved-ambiguous"
            if owners
            else "unresolved"
            if matches
            else "unknown"
        ),
        "distribution_nodes": owners,
        "ownership_completeness": completeness,
        "observed_contexts": sorted({str(row["context"]) for row in matches}),
        "evidence_sources": sorted(
            {
                str(source_id)
                for row in matches
                for source_id in cast(
                    "Sequence[object]", row.get("evidence_sources", ())
                )
            }
        ),
    }


def _dependency_provenance(
    observation: Mapping[str, object], source_ids: set[str]
) -> dict[str, object]:
    sources = cast("Sequence[Mapping[str, object]]", observation["evidence_sources"])
    return {
        "observation_identity": observation["observation_identity"],
        "producer": deepcopy(observation["producer"]),
        "repository_binding": deepcopy(observation["repository_binding"]),
        "evidence_sources": [
            deepcopy(row) for row in sources if str(row["source_id"]) in source_ids
        ],
    }


class DependencyResolutionCorrelationMixin:
    @staticmethod
    def _import_ownership_matches(
        ownership: Sequence[Mapping[str, object]],
        candidates: Sequence[str],
        context: str | None,
    ) -> list[Mapping[str, object]]:
        contexts = (
            [context]
            if context is not None
            else sorted({str(row["context"]) for row in ownership})
        )
        selected: list[Mapping[str, object]] = []
        for current_context in contexts:
            for module in candidates:
                matches = [
                    row
                    for row in ownership
                    if row["context"] == current_context and row["module"] == module
                ]
                if matches:
                    selected.extend(matches)
                    break
        return selected

    def dependency_import_correspondence(
        self,
        observation: Mapping[str, object],
        *,
        source_path: str,
        import_target: str,
        context: str | None = None,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._require_current_dependency_observation_v3(observation)
        candidates = self._python_import_module_candidates(source_path, import_target)
        ownership = cast(
            "Sequence[Mapping[str, object]]", observation["module_ownership"]
        )
        matches = self._import_ownership_matches(ownership, candidates, context)
        summary = _ownership_summary(matches)
        source_ids = cast("list[str]", summary["evidence_sources"])
        return {
            "source_path": source_path,
            "import_target": import_target,
            **({"context": context} if context is not None else {}),
            "import_claim_authority": "caller-claimed",
            "repository_paths": self._resolve_import_paths(source_path, import_target),
            "matched_modules": [
                {
                    "context": row["context"],
                    "module": row["module"],
                    "evidence_sources": list(
                        cast("Sequence[str]", row["evidence_sources"])
                    ),
                }
                for row in matches
            ],
            **summary,
            "dependency_provenance": _dependency_provenance(
                observation, set(source_ids)
            ),
            "authority": "qualified-external-observation",
            "producer_authority": "caller-claimed",
            "causation": "not-inferred",
        }

    def _dependency_correlation_row_definition(
        self,
        raw: Mapping[str, object],
    ) -> tuple[dict[str, object], list[Mapping[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        _contract.reject_unknown_fields(raw, label="correlation row")
        module = _text(raw.get("module"), label="correlation module", required=True)
        context = _text(raw.get("context"), label="correlation context")
        anchors = _objects(
            raw.get("anchors", ()), label="correlation anchors", limit=256
        )
        normalized_anchors: list[dict[str, object]] = []
        for anchor in anchors:
            claims = self._anchor_claims(anchor)
            normalized_anchors.append(
                {"anchor_id": claims.anchor_id, "claims": claims.as_dict()}
            )
        normalized_anchors.sort(key=lambda row: str(row["anchor_id"]))
        definition: dict[str, object] = {
            "module": module,
            "context": context or None,
            "completeness": str(raw.get("completeness") or "unknown").strip(),
            "truncation": str(raw.get("truncation") or "unknown").strip(),
            "anchors": normalized_anchors,
        }
        return definition, anchors

    @staticmethod
    def _exact_ownership_matches(
        ownership: Sequence[Mapping[str, object]],
        module: str,
        context: str | None,
    ) -> list[Mapping[str, object]]:
        return [
            row
            for row in ownership
            if row["module"] == module
            and (context is None or row["context"] == context)
        ]

    def _dependency_correlation_bundle(
        self,
        definition: Mapping[str, object],
        anchors: Sequence[Mapping[str, object]],
        observation: Mapping[str, object],
        bundle_id: str,
    ) -> dict[str, object]:
        module = str(definition["module"])
        context = definition["context"]
        return {
            "bundle_id": bundle_id,
            "producer": {
                "kind": "dependency-correlation-adapter",
                "resolution_identity": observation["resolution_identity"],
                "observation_identity": observation["observation_identity"],
            },
            "completeness": definition["completeness"],
            "scope": {
                "kind": "dependency-module-correlation",
                "module": module,
                **({"context": context} if context is not None else {}),
            },
            "truncation": definition["truncation"],
            "anchors": list(anchors),
        }

    def _dependency_correlation_item(
        self,
        raw: Mapping[str, object],
        observation: Mapping[str, object],
        ownership: Sequence[Mapping[str, object]],
        occurrences: dict[str, int],
    ) -> tuple[dict[str, object], dict[str, object], list[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        definition, anchors = self._dependency_correlation_row_definition(raw)
        digest = self._packet_digest(
            "hashmarks.dependency-correlation-bundle.v2", definition
        )
        ordinal = occurrences.get(digest, 0)
        occurrences[digest] = ordinal + 1
        bundle_id = f"dependency-correlation:{digest}:{ordinal}"
        module = str(definition["module"])
        context = cast("str | None", definition["context"])
        matches = self._exact_ownership_matches(ownership, module, context)
        summary = _ownership_summary(matches)
        source_ids = cast("list[str]", summary["evidence_sources"])
        link = {
            "bundle_id": bundle_id,
            "module": module,
            **({"context": context} if context else {}),
            **summary,
            "observation_identity": observation["observation_identity"],
            "authority": "qualified-external-observation",
            "producer_authority": "caller-claimed",
            "causation": "not-inferred",
        }
        bundle = self._dependency_correlation_bundle(
            definition, anchors, observation, bundle_id
        )
        return bundle, link, source_ids

    def dependency_evidence_correlation(
        self,
        observation: Mapping[str, object],
        request: Mapping[str, object],
    ) -> dict[str, object]:
        """Correlate dependency owners with current repository evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._require_current_dependency_observation_v3(observation)
        _contract.reject_unknown_fields(request, label="correlation request")
        correlations = _objects(
            request.get("correlations", ()), label="correlations", limit=256
        )
        ownership = cast(
            "Sequence[Mapping[str, object]]", observation["module_ownership"]
        )
        bundles: list[dict[str, object]] = []
        dependency_links: list[dict[str, object]] = []
        used_sources: set[str] = set()
        occurrences: dict[str, int] = {}
        for raw in correlations:
            bundle, link, source_ids = self._dependency_correlation_item(
                raw, observation, ownership, occurrences
            )
            used_sources.update(source_ids)
            dependency_links.append(link)
            bundles.append(bundle)
        packet = self.correlate_evidence(
            bundles,
            path_mappings=cast(
                "Sequence[Mapping[str, object]] | None",
                request.get("path_mappings"),
            ),
        )
        return {
            "schema": "hashmarks.dependency-evidence-correlation.v2",
            "resolution_identity": observation["resolution_identity"],
            "observation_identity": observation["observation_identity"],
            "dependency_provenance": _dependency_provenance(observation, used_sources),
            "correlation": packet,
            "dependency_links": sorted(
                dependency_links, key=lambda row: str(row["bundle_id"])
            ),
            "authority": "repository-intelligence-only",
            "producer_authority": "caller-claimed",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
        }
