from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_schema, validate_operation_response
from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap


class ScopedSourceLiteralsMixin:
    """Explicit multi-literal composition over the canonical source observer."""

    def _scoped_literal_set_member(
        self,
        path: str,
        literals: tuple[str, ...],
        *,
        remaining_bytes: int,
        max_member_bytes: int,
        limit: int,
        context_lines: int,
    ) -> tuple[dict[str, object], dict[str, list[dict[str, object]]], int]:
        """Observe one canonical byte capture for every requested literal."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        empty: dict[str, list[dict[str, object]]] = {
            literal: [] for literal in literals
        }
        if remaining_bytes < 1:
            return (
                {
                    "path": path,
                    "state": "unknown",
                    "reason": "scope-byte-budget-exhausted",
                    "availability": "unavailable",
                    "observed_match_counts": None,
                },
                empty,
                0,
            )
        member, raw = self._bounded_source_observation(
            path, min(remaining_bytes, max_member_bytes)
        )
        record = {
            "path": path,
            "state": member["state"],
            "reason": member.get("reason"),
            "member_revision": member.get("member_revision"),
            "availability": "unavailable",
            "observed_match_counts": None,
        }
        if raw is None:
            return record, empty, 0
        if b"\x00" in raw:
            record.update(availability="unsupported", reason="null-byte-text")
            return record, empty, len(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            record.update(availability="unsupported", reason="invalid-utf8")
            return record, empty, len(raw)
        symbols = (
            self.store.symbols_for_path(path)
            if member.get("index_state") == "indexed"
            else []
        )
        token_kinds = self._python_source_token_kinds(text, path)
        counts: dict[str, int] = {}
        for literal in literals:
            hits, count = self._source_occurrences(
                text,
                literal,
                member=member,
                limit=limit,
                symbols=symbols,
                token_kinds=token_kinds,
            )
            self._source_evidenced_hits(
                hits, text=text, literal=literal, context_lines=context_lines
            )
            empty[literal] = hits
            counts[literal] = count
        record.update(
            availability="observed",
            observed_match_counts=counts,
            returned_occurrence_count=sum(len(rows) for rows in empty.values()),
        )
        return record, empty, len(raw)

    def scoped_source_literals(
        self,
        paths: Sequence[str],
        literals: Sequence[str],
        *,
        limit: int = 100,
        max_total_bytes: int = 4_194_304,
        max_member_bytes: int = 1_048_576,
        context_lines: int = 0,
    ) -> dict[str, object]:
        """Bounded literal-set evidence, sharing each stable member byte read."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if isinstance(paths, (str, bytes)) or not 1 <= len(paths) <= 32:
            raise ValueError("scope must contain between 1 and 32 explicit paths")
        if isinstance(literals, (str, bytes)) or not 1 <= len(literals) <= 8:
            raise ValueError("literals must contain between 1 and 8 exact strings")
        if any(not isinstance(value, str) for value in literals):
            raise ValueError("literals must contain only strings")
        if len(set(literals)) != len(literals):
            raise ValueError("literals must be distinct")
        if not 1 <= max_total_bytes <= 8_388_608:
            raise ValueError("max_total_bytes must be between 1 and 8388608")
        if type(context_lines) is not int or context_lines not in (0, 1):
            raise ValueError("context_lines must be 0 or 1")
        for literal in literals:
            self._validate_source_observation(literal, limit, max_member_bytes, 2_000)
        selected_paths = sorted(
            {normalize_relative_path(path, allow_root=False) for path in paths}
        )
        selected_literals = tuple(sorted(literals))
        generation_before = self.store.generation()
        members: list[dict[str, object]] = []
        observed_bytes = 0
        complete = True
        observed_counts = dict.fromkeys(selected_literals, 0)
        hits_by_literal: dict[str, list[dict[str, object]]] = {
            literal: [] for literal in selected_literals
        }
        for path in selected_paths:
            record, member_hits, source_bytes = self._scoped_literal_set_member(
                path,
                selected_literals,
                remaining_bytes=max_total_bytes - observed_bytes,
                max_member_bytes=max_member_bytes,
                limit=limit,
                context_lines=context_lines,
            )
            members.append(record)
            observed_bytes += source_bytes
            member_counts = record["observed_match_counts"]
            if not isinstance(member_counts, dict):
                complete = False
                continue
            for literal in selected_literals:
                observed_counts[literal] += cast("int", member_counts[literal])
                selected = hits_by_literal[literal]
                selected.extend(member_hits[literal][: max(0, limit - len(selected))])
        occurrences: list[dict[str, object]] = []
        # One hit per literal per round prevents the first term from consuming
        # all presentation slots. Each term's hits retain path/line order.
        for index in range(limit):
            for literal in selected_literals:
                if index < len(hits_by_literal[literal]):
                    occurrences.append(hits_by_literal[literal][index])
                    if len(occurrences) == limit:
                        break
            if len(occurrences) == limit:
                break
        generation, identity_generation, stale = self._generation_status()
        coverage = complete and generation == generation_before
        freshness = (
            freshness_state(stale) if coverage else "stale"
        )
        exact = sum(observed_counts.values()) if coverage else None
        truncated = sum(observed_counts.values()) > len(occurrences)
        qualified = coverage and freshness == "current"
        result: dict[str, object] = {
            "schema": operation_schema("source_observation", "literals"),
            "observation_scope": "explicit-member-and-literal-set-only",
            "paths": selected_paths,
            "literals": list(selected_literals),
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": freshness,
            "member_observations": members,
            "literal_observations": [
                {
                    "literal": literal,
                    "observed_match_count": observed_counts[literal],
                    "exact_match_count": observed_counts[literal] if coverage else None,
                    "returned_occurrence_count": sum(
                        row["literal"] == literal for row in occurrences
                    ),
                    "negative_evidence": (
                        "admissible-within-explicit-member-set"
                        if qualified and observed_counts[literal] == 0
                        else "not-admissible"
                    ),
                }
                for literal in selected_literals
            ],
            "source_coverage": "complete" if coverage else "unknown",
            "observed_match_count": sum(observed_counts.values()),
            "exact_match_count": exact,
            "occurrences": occurrences,
            "selection_order": "round-robin-by-literal",
            "completeness": (
                "unknown" if not coverage else "incomplete" if truncated else "complete"
            ),
            "truncation": (
                "unknown" if not coverage else "truncated" if truncated else "complete"
            ),
            "negative_evidence": (
                "admissible-within-explicit-member-and-literal-set"
                if qualified and exact == 0
                else "not-admissible"
            ),
            "limits": {
                "returned_occurrences": limit,
                "max_total_bytes": max_total_bytes,
                "max_member_bytes": max_member_bytes,
                "literal_count": len(selected_literals),
                "context_lines": context_lines,
            },
            "observed_source_bytes": observed_bytes,
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        result["observation_identity"] = self._evidence_identity(
            operation_schema("source_observation", "literals"), result
        )
        return validate_operation_response(
            "source_observation", result, mode="literals"
        )

