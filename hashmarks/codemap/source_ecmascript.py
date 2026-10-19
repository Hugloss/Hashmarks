"""Native ECMAScript syntax observations over canonical Source member bytes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_response

from .ecmascript_syntax import (
    ECMASCRIPT_SOURCE_SCHEMA,
    EXPRESSION_PREVIEW_BYTES,
    FACT_KINDS,
    MAX_SYNTAX_NODES,
    SyntaxObservationBound,
    ecmascript_facts,
)
from .providers import SourceSyntaxProvider
from .repository_observation import evidence_identity
from .source_languages import SOURCE_LANGUAGES

if TYPE_CHECKING:
    from .repository_source import RepositorySource


def _syntax_evidence(
    provider: SourceSyntaxProvider,
    raw: bytes,
    grammar: str,
    limit: int,
) -> dict[str, object]:
    """Unsupported capability and recovered syntax never become empty evidence."""
    if b"\x00" in raw:
        return {"reason": "null-byte-text"}
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"reason": "invalid-utf8"}
    try:
        tree = provider.syntax_tree(raw, grammar)
        if tree is None:
            return {"reason": "native-syntax-unavailable"}
        facts, count = ecmascript_facts(tree, raw, limit)
    except SyntaxObservationBound:
        return {"reason": "native-syntax-node-bound"}
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return {"reason": "native-syntax-parse-failed"}
    clipped = count > len(facts)
    return {
        "availability": "observed",
        "completeness": "incomplete" if clipped else "complete",
        "truncation": "truncated" if clipped else "not-truncated",
        "facts": facts,
        "observed_fact_count": count,
        "returned_fact_count": len(facts),
        "reason": None,
    }


class SourceEcmascriptMixin:
    """A Source projection, sharing the configured range provider and member read."""

    def _ecmascript_packet(
        self, member: dict[str, object], limit: int, max_bytes: int
    ) -> dict[str, object]:
        return {
            "schema": ECMASCRIPT_SOURCE_SCHEMA,
            "member": member,
            "observation_scope": "exact-admitted-member-native-syntax",
            "coordinate_system": "zero-based-half-open-bytes",
            "limits": {
                "results": limit,
                "max_bytes": max_bytes,
                "max_syntax_nodes": MAX_SYNTAX_NODES,
                "expression_preview_bytes": EXPRESSION_PREVIEW_BYTES,
            },
            "coverage": {
                "fact_kinds": list(FACT_KINDS),
                "destructuring": "object-pattern-components",
                "expression_text": "bounded-preview",
                "semantic_resolution": "not-performed",
            },
            "availability": "unavailable",
            "completeness": "unknown",
            "truncation": "unknown",
            "facts": [],
            "observed_fact_count": None,
            "returned_fact_count": 0,
            "observation_identity": None,
            "semantic_resolution": "not-performed",
            "reason": member.get("reason"),
            "negative_evidence": "not-admissible",
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }

    def _ecmascript_observe(self, packet: dict[str, object], raw: bytes | None) -> None:
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        member = cast("dict[str, object]", packet["member"])
        suffix = Path(str(member["path"])).suffix.lower()
        language = SOURCE_LANGUAGES.get(suffix)
        grammar = (
            ("tsx" if suffix == ".tsx" else language)
            if language in {"javascript", "typescript"}
            else None
        )
        provider = self.index.range_provider
        syntax_provider = isinstance(provider, SourceSyntaxProvider)
        signature = provider.signature(grammar or "") if syntax_provider else None
        packet.update(
            language=language,
            parser={
                "capability": provider.status().as_dict(),
                "grammar": grammar,
                "signature": signature,
            },
        )
        if raw is None:
            return
        if language not in {"javascript", "typescript"}:
            packet["reason"] = "unsupported-source-language"
            return
        if not syntax_provider or signature is None:
            packet["reason"] = "native-syntax-unavailable"
            return
        limits = cast("dict[str, int]", packet["limits"])
        packet.update(_syntax_evidence(provider, raw, str(grammar), limits["results"]))

    @staticmethod
    def _ecmascript_identities(packet: dict[str, object]) -> None:
        if packet["availability"] != "observed":
            return
        binding = {"member": packet["member"], "parser": packet["parser"]}
        for fact in cast("list[dict[str, object]]", packet["facts"]):
            fact["evidence_identity"] = evidence_identity(
                "hashmarks.ecmascript-syntax-fact.v1", {**binding, "fact": fact}
            )
        packet["observation_identity"] = evidence_identity(
            ECMASCRIPT_SOURCE_SCHEMA,
            {
                **binding,
                "coverage": packet["coverage"],
                "facts": packet["facts"],
                "observed_fact_count": packet["observed_fact_count"],
                "truncation": packet["truncation"],
            },
        )

    @operation_response("source_ecmascript")
    def ecmascript(
        self,
        relpath: str,
        *,
        limit: int = 200,
        max_bytes: int = 1_048_576,
    ) -> dict[str, object]:
        """Observe exact native syntax, with no alias closure or resolved call target.

        Coverage describes listed syntax categories in this one member. Dynamic
        values, imported implementations, execution, and semantic absence remain
        outside the observation. Native parser failure supplies unknown evidence.
        """
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 8_388_608:
            raise ValueError("max_bytes must be between 1 and 8388608")
        generation_before = self.store.generation()
        member, raw = self._bounded_source_observation(relpath, max_bytes)
        packet = self._ecmascript_packet(member, limit, max_bytes)
        self._ecmascript_observe(packet, raw)
        generation, identity_generation, stale = self.reads.generation_status()
        packet.update(
            generation=generation,
            identity_generation=identity_generation,
            freshness="stale"
            if generation != generation_before
            else freshness_state(stale),
        )
        self._ecmascript_identities(packet)
        return packet
