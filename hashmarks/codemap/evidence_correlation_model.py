"""Pure correspondence values: declared definitions, equivalence and completeness."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import cast


class CorrelationValues:
    @staticmethod
    def _equivalence(
        anchor: Mapping[str, object],
        binding: Mapping[str, object],
    ) -> dict[str, object]:
        claims = anchor.get("claims")
        evidence = binding.get("evidence")
        if not isinstance(claims, Mapping):
            return {"state": "unknown", "basis": []}
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
            return {"state": "unknown", "basis": []}
        rows = [row for row in evidence if isinstance(row, Mapping)]
        if len(rows) != 1:
            return {"state": "unknown", "basis": []}
        return CorrelationValues._equivalence_for_row(claims, rows[0])

    @staticmethod
    def _equivalence_for_row(
        claims: Mapping[str, object],
        observed: Mapping[str, object],
    ) -> dict[str, object]:
        basis: list[dict[str, object]] = []
        unchecked = False
        for claim_key, observed_key, kind in (
            ("member_revision", "member_revision", "member-revision"),
            ("span_identity", "span_identity", "span-identity"),
        ):
            if claims.get(claim_key) is None:
                continue
            if observed.get(observed_key) is None:
                unchecked = True
                continue
            basis.append(
                {
                    "kind": kind,
                    "matched": str(claims[claim_key]) == str(observed[observed_key]),
                }
            )
        if any(not row["matched"] for row in basis):
            state = "mismatch"
        elif unchecked or not basis:
            state = "unknown"
        else:
            state = "proven"
        return {"state": state, "basis": basis}

    @staticmethod
    def _correlation_binding_rows(
        repository_evidence: Mapping[str, object],
    ) -> dict[str, Mapping[str, object]]:
        rows = repository_evidence.get("bindings", [])
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return {}
        return {
            str(row["binding_id"]): row
            for row in rows
            if isinstance(row, Mapping) and row.get("binding_id") is not None
        }

    @staticmethod
    def _definition(
        bundles: Sequence[Mapping[str, object]],
        *,
        mappings: Sequence[Mapping[str, str]],
        include_relationships: bool,
        relationship_limit_per_path: int,
    ) -> dict[str, object]:
        declarations = [
            CorrelationValues._bundle_definition(bundle) for bundle in bundles
        ]
        declarations.sort(key=lambda row: str(row["bundle_id"]))
        return {
            "path_mappings": list(mappings),
            "bundles": declarations,
            "include_relationships": include_relationships,
            "relationship_limit_per_path": (
                relationship_limit_per_path if include_relationships else None
            ),
        }

    @staticmethod
    def _bundle_definition(
        bundle: Mapping[str, object],
    ) -> dict[str, object]:
        anchors = cast(Iterable[object], bundle.get("anchors", []))
        return {
            "bundle_id": bundle.get("bundle_id"),
            "producer": bundle.get("producer", {}),
            "provenance": bundle.get("provenance", {}),
            "completeness": bundle.get("completeness"),
            "scope": bundle.get("scope", {}),
            "truncation": bundle.get("truncation", "unknown"),
            "anchors": [
                {
                    "anchor_id": anchor.get("anchor_id"),
                    "claims": anchor.get("claims", {}),
                }
                for anchor in anchors
                if isinstance(anchor, Mapping)
            ],
        }

    @staticmethod
    def _correspondence_target(
        anchor: Mapping[str, object],
    ) -> tuple[str, str, int, int] | None:
        resolution = anchor.get("resolution")
        if not isinstance(resolution, Mapping):
            return None
        if resolution.get("state") != "resolved-unique":
            return None
        path = resolution.get("repository_path")
        if not isinstance(path, str):
            return None
        symbol = resolution.get("symbol")
        if not isinstance(symbol, Mapping):
            return path, "", 0, 0
        return (
            path,
            str(symbol.get("name") or ""),
            int(symbol.get("start_line") or 0),
            int(symbol.get("end_line") or 0),
        )

    @staticmethod
    def _cross_bundle_correspondence(
        bundles: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        groups: dict[tuple[str, str, int, int], list[dict[str, str]]] = {}
        for bundle in bundles:
            bundle_id = str(bundle.get("bundle_id") or "")
            anchors = bundle.get("anchors", [])
            if not isinstance(anchors, Sequence) or isinstance(anchors, (str, bytes)):
                continue
            for anchor in anchors:
                if not isinstance(anchor, Mapping):
                    continue
                key = CorrelationValues._correspondence_target(anchor)
                if key is None:
                    continue
                groups.setdefault(key, []).append(
                    {
                        "bundle_id": bundle_id,
                        "anchor_id": str(anchor.get("anchor_id") or ""),
                    }
                )
        rows: list[dict[str, object]] = []
        for (path, symbol, start_line, end_line), observations in sorted(
            groups.items()
        ):
            bundle_ids = {row["bundle_id"] for row in observations}
            if len(bundle_ids) < 2:
                continue
            rows.append(
                {
                    "state": "same-repository-target",
                    "scope": "symbol" if symbol else "member",
                    "repository_path": path,
                    **(
                        {
                            "symbol": symbol,
                            "start_line": start_line,
                            "end_line": end_line,
                        }
                        if symbol
                        else {}
                    ),
                    "observations": sorted(
                        observations,
                        key=lambda row: (row["bundle_id"], row["anchor_id"]),
                    ),
                    "causation": "not-inferred",
                    "incident_identity": "not-inferred",
                }
            )
        return rows

    @staticmethod
    def _overall_completeness(
        bundles: Sequence[Mapping[str, object]],
    ) -> dict[str, str]:
        states = [str(bundle.get("completeness") or "unknown") for bundle in bundles]
        truncations = [str(bundle.get("truncation") or "unknown") for bundle in bundles]
        if "incomplete" in states or "truncated" in truncations:
            state = "incomplete"
        elif (
            states
            and all(item == "complete" for item in states)
            and all(item == "complete" for item in truncations)
        ):
            state = "complete"
        else:
            state = "unknown"
        return {
            "state": state,
            "scope": "caller-declared-external-observations",
            "authority": "caller-claimed",
            "negative_evidence": (
                "admissible-within-declared-scopes"
                if state == "complete"
                else "not-admissible"
            ),
        }
