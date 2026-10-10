from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_schema, validate_operation_response
from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass(slots=True)
class _LiteralSetState:
    """Request-scoped aggregation; never an independent source/index owner."""

    paths: list[str]
    literals: tuple[str, ...]
    start_generation: int
    limit: int
    max_total_bytes: int
    max_member_bytes: int
    context_lines: int
    members: list[dict[str, object]] = field(default_factory=list)
    observed_bytes: int = 0
    complete: bool = True
    counts: dict[str, int] = field(init=False)
    hits: dict[str, list[dict[str, object]]] = field(init=False)

    def __post_init__(self) -> None:
        self.counts = dict.fromkeys(self.literals, 0)
        self.hits = {literal: [] for literal in self.literals}

    def add(
        self,
        record: dict[str, object],
        hits: dict[str, list[dict[str, object]]],
        consumed: int,
    ) -> None:
        self.members.append(record)
        self.observed_bytes += consumed
        counts = record["observed_match_counts"]
        if not isinstance(counts, dict):
            self.complete = False
            return
        for literal in self.literals:
            self.counts[literal] += cast("int", counts[literal])
            selected = self.hits[literal]
            selected.extend(hits[literal][: max(0, self.limit - len(selected))])

    def selected_hits(self) -> list[dict[str, object]]:
        """Balance capped rows across literals, preserving each term's file order."""
        selected: list[dict[str, object]] = []
        for index in range(self.limit):
            for literal in self.literals:
                if index < len(self.hits[literal]):
                    selected.append(self.hits[literal][index])
                    if len(selected) == self.limit:
                        return selected
        return selected


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

    @staticmethod
    def _validated_literal_set(literals: Sequence[str]) -> tuple[str, ...]:
        if isinstance(literals, (str, bytes)) or not 1 <= len(literals) <= 8:
            raise ValueError("literals must contain between 1 and 8 exact strings")
        if any(not isinstance(value, str) for value in literals):
            raise ValueError("literals must contain only strings")
        if len(set(literals)) != len(literals):
            raise ValueError("literals must be distinct")
        return tuple(sorted(literals))

    @staticmethod
    def _validated_literal_paths(paths: Sequence[str]) -> list[str]:
        if isinstance(paths, (str, bytes)) or not 1 <= len(paths) <= 32:
            raise ValueError("scope must contain between 1 and 32 explicit paths")
        return sorted(
            {normalize_relative_path(path, allow_root=False) for path in paths}
        )

    def _literal_set_request(
        self,
        paths: Sequence[str],
        literals: Sequence[str],
        limit: int,
        max_total_bytes: int,
        max_member_bytes: int,
        context_lines: int,
    ) -> tuple[list[str], tuple[str, ...]]:
        """Reject invalid input before source observation and generation reads."""
        if not 1 <= max_total_bytes <= 8_388_608:
            raise ValueError("max_total_bytes must be between 1 and 8388608")
        if type(context_lines) is not int or context_lines not in (0, 1):
            raise ValueError("context_lines must be 0 or 1")
        selected_literals = self._validated_literal_set(literals)
        selected_paths = self._validated_literal_paths(paths)
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for literal in selected_literals:
            self._validate_source_observation(
                literal, limit, max_member_bytes, 2_000
            )
        return selected_paths, selected_literals

    def _literal_set_result(self, state: _LiteralSetState) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation, identity_generation, stale = self._generation_status()
        coverage = state.complete and generation == state.start_generation
        freshness = freshness_state(stale) if coverage else "stale"
        selected = state.selected_hits()
        count = sum(state.counts.values())
        exact = count if coverage else None
        truncated = count > len(selected)
        qualified = coverage and freshness == "current"
        result: dict[str, object] = {
            "schema": operation_schema("source_observation", "literals"),
            "observation_scope": "explicit-member-and-literal-set-only",
            "paths": state.paths,
            "literals": list(state.literals),
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": freshness,
            "member_observations": state.members,
            "literal_observations": [
                {
                    "literal": literal,
                    "observed_match_count": state.counts[literal],
                    "exact_match_count": state.counts[literal] if coverage else None,
                    "returned_occurrence_count": sum(
                        row["literal"] == literal for row in selected
                    ),
                    "negative_evidence": (
                        "admissible-within-explicit-member-set"
                        if qualified and state.counts[literal] == 0
                        else "not-admissible"
                    ),
                }
                for literal in state.literals
            ],
            "source_coverage": "complete" if coverage else "unknown",
            "observed_match_count": count,
            "exact_match_count": exact,
            "occurrences": selected,
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
                "returned_occurrences": state.limit,
                "max_total_bytes": state.max_total_bytes,
                "max_member_bytes": state.max_member_bytes,
                "literal_count": len(state.literals),
                "context_lines": state.context_lines,
            },
            "observed_source_bytes": state.observed_bytes,
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        result["observation_identity"] = self._evidence_identity(
            operation_schema("source_observation", "literals"), result
        )
        return validate_operation_response(
            "source_observation", result, mode="literals"
        )

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
        """One stable source read per member, with qualified per-literal counts."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        selected_paths, selected_literals = self._literal_set_request(
            paths, literals, limit, max_total_bytes, max_member_bytes, context_lines
        )
        state = _LiteralSetState(
            paths=selected_paths,
            literals=selected_literals,
            start_generation=self.store.generation(),
            limit=limit,
            max_total_bytes=max_total_bytes,
            max_member_bytes=max_member_bytes,
            context_lines=context_lines,
        )
        for path in state.paths:
            record, hits, consumed = self._scoped_literal_set_member(
                path,
                state.literals,
                remaining_bytes=state.max_total_bytes - state.observed_bytes,
                max_member_bytes=state.max_member_bytes,
                limit=state.limit,
                context_lines=state.context_lines,
            )
            state.add(record, hits, consumed)
        return self._literal_set_result(state)
