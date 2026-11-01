"""Source-local binding observations over canonical admitted syntax and bytes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks import python_ast_cache
from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_response, operation_schema

from .ecmascript_bindings import ecmascript_bindings
from .ecmascript_syntax import EXPRESSION_PREVIEW_BYTES, SyntaxObservationBound
from .providers import (
    SourceSyntaxError,
    SourceSyntaxProvider,
    source_grammar,
    syntax_session,
)
from .python_bindings import python_bindings
from .repository_observation import evidence_identity
from .source_binding_contract import (
    BINDING_FACT_KINDS,
    BINDING_INTERPRETER_SIGNATURE,
    MAX_ALIAS_DEPTH,
    MAX_BINDING_EXPRESSION_DEPTH,
    MAX_BINDING_NODES,
    MAX_BINDING_SUPPORTING_RANGES,
    MAX_HELPER_EDGES,
    MAX_LITERAL_BYTES,
    BindingObservationBound,
)
from .source_languages import SOURCE_LANGUAGES

if TYPE_CHECKING:
    from .providers import SourceRangeProvider
    from .repository_source import RepositorySource

SOURCE_BINDINGS_SCHEMA = operation_schema("source_bindings")


def _binding_parser(provider: SourceRangeProvider, path: str) -> dict[str, object]:
    language = SOURCE_LANGUAGES.get(Path(path).suffix.lower())
    if language == "python":
        signature = python_ast_cache.python_ast_signature()
        return {
            "grammar": "python",
            "signature": signature,
            "capability": {"name": "python-ast", "available": True},
        }
    grammar = source_grammar(path)
    return {
        "grammar": grammar,
        "signature": provider.signature(grammar or "")
        if isinstance(provider, SourceSyntaxProvider)
        else None,
        "capability": provider.status().as_dict(),
    }


def _binding_projection(
    provider: SourceRangeProvider, raw: bytes, grammar: str, limit: int
) -> tuple[list[dict[str, object]], int]:
    if grammar == "python":
        return python_bindings(python_ast_cache.parse_python_ast(raw), raw, limit)
    if not isinstance(provider, SourceSyntaxProvider):
        raise SourceSyntaxError("native-syntax-unavailable")
    tree = provider.syntax_tree(raw, grammar)
    if tree is None:
        raise SourceSyntaxError("native-syntax-unavailable")
    return ecmascript_bindings(tree, raw, limit)


def _binding_evidence(
    provider: SourceRangeProvider, raw: bytes, grammar: str, limit: int
) -> dict[str, object]:
    """A failed full-scope qualification never returns a partial binding table."""
    try:
        projection = _binding_projection(provider, raw, grammar, limit)
    except (BindingObservationBound, SyntaxObservationBound):
        return {"reason": "source-binding-observation-bound"}
    except SourceSyntaxError as exc:
        return {"reason": exc.reason}
    except UnicodeError:
        return {"reason": "invalid-utf8"}
    except (SyntaxError, ValueError, RecursionError):
        return {"reason": "source-binding-syntax-unqualified"}
    except (ImportError, LookupError, OSError, RuntimeError, TypeError):
        return {"reason": "source-binding-provider-failed"}
    facts, count = projection
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


def _binding_packet(
    member: dict[str, object], limit: int, max_bytes: int
) -> dict[str, object]:
    return {
        "schema": SOURCE_BINDINGS_SCHEMA,
        "member": member,
        "language": SOURCE_LANGUAGES.get(Path(str(member["path"])).suffix.lower()),
        "observation_scope": "exact-admitted-member-source-bindings",
        "coordinate_system": "zero-based-half-open-bytes",
        "producer": {"binding_interpreter": BINDING_INTERPRETER_SIGNATURE},
        "limits": {
            "results": limit,
            "max_bytes": max_bytes,
            "max_syntax_nodes": MAX_BINDING_NODES,
            "max_alias_depth": MAX_ALIAS_DEPTH,
            "max_expression_depth": MAX_BINDING_EXPRESSION_DEPTH,
            "max_supporting_ranges": MAX_BINDING_SUPPORTING_RANGES,
            "max_import_hops": 0,
            "max_helper_edges": MAX_HELPER_EDGES,
            "max_literal_bytes": MAX_LITERAL_BYTES,
            "expression_preview_bytes": EXPRESSION_PREVIEW_BYTES,
        },
        "coverage": {
            "fact_kinds": list(BINDING_FACT_KINDS),
            "qualification_scope": "complete-bounded-member-before-projection",
            "expression_text": "bounded-preview",
            "import_resolution": "not-performed",
        },
        "semantic_coverage": {
            "state": "incomplete",
            "basis": "bounded-supported-source-forms",
            "unknowns": "explicit-per-fact-reasons",
            "cross_member_resolution": "not-performed",
        },
        "availability": "unavailable",
        "completeness": "unknown",
        "truncation": "unknown",
        "facts": [],
        "observed_fact_count": None,
        "returned_fact_count": 0,
        "observation_identity": None,
        "runtime_target_resolution": "not-performed",
        "module_resolution": "not-performed",
        "reason": member.get("reason"),
        "negative_evidence": "not-admissible",
        "authority": "repository-evidence-only",
        "execution_effect": "none",
    }


def _binding_identities(packet: dict[str, object]) -> None:
    if packet["availability"] != "observed":
        return
    binding = {
        "member": packet["member"],
        "parser": packet["parser"],
        "producer": packet["producer"],
    }
    for fact in cast("list[dict[str, object]]", packet["facts"]):
        fact["evidence_identity"] = evidence_identity(
            "hashmarks.source-binding-fact.v1", {**binding, "fact": fact}
        )
    packet["observation_identity"] = evidence_identity(
        SOURCE_BINDINGS_SCHEMA,
        {
            **binding,
            "coverage": packet["coverage"],
            "semantic_coverage": packet["semantic_coverage"],
            "facts": packet["facts"],
            "observed_fact_count": packet["observed_fact_count"],
            "truncation": packet["truncation"],
        },
    )


class SourceBindingsMixin:
    """Reuse Source admission, freshness and existing per-language syntax owners."""

    def _bindings_observe(self, packet: dict[str, object], raw: bytes | None) -> None:
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        member = cast("dict[str, object]", packet["member"])
        parser = _binding_parser(self.index.range_provider, str(member["path"]))
        packet["parser"] = parser
        if raw is None:
            return
        if packet["language"] not in {"python", "javascript", "typescript"}:
            packet["reason"] = "unsupported-source-language"
            return
        if parser["signature"] is None:
            packet["reason"] = "native-syntax-unavailable"
            return
        limits = cast("dict[str, int]", packet["limits"])
        packet.update(
            _binding_evidence(
                self.index.range_provider,
                raw,
                str(parser["grammar"]),
                limits["results"],
            )
        )

    def _bindings_recheck(self, packet: dict[str, object]) -> bool:
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        if packet["availability"] != "observed":
            return False
        member = cast("dict[str, object]", packet["member"])
        limits = cast("dict[str, int]", packet["limits"])
        path = str(member["path"])
        current, _ = self._bounded_source_observation(path, limits["max_bytes"])
        changed = (
            "source-changed-during-observation"
            if current != member
            else "source-binding-producer-changed"
            if _binding_parser(self.index.range_provider, path) != packet["parser"]
            or packet["producer"]
            != {"binding_interpreter": BINDING_INTERPRETER_SIGNATURE}
            else None
        )
        if changed is None:
            return False
        packet.update(_binding_packet(member, limits["results"], limits["max_bytes"]))
        packet["reason"] = changed
        return True

    def _bindings_observation(
        self, relpath: str, limit: int, max_bytes: int
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        before = self.store.generation()
        member, raw = self._bounded_source_observation(relpath, max_bytes)
        packet = _binding_packet(member, limit, max_bytes)
        self._bindings_observe(packet, raw)
        changed = self._bindings_recheck(packet)
        generation, identity_generation, stale = self.reads.generation_status()
        packet.update(
            generation=generation,
            identity_generation=identity_generation,
            freshness="stale"
            if changed or generation != before
            else freshness_state(stale),
        )
        _binding_identities(packet)
        return packet

    @operation_response("source_bindings")
    def bindings(
        self, relpath: str, *, limit: int = 200, max_bytes: int = 1_048_576
    ) -> dict[str, object]:
        """Observe bounded source origins, preserving unknown runtime targets."""
        if TYPE_CHECKING:
            self = cast("RepositorySource", self)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 8_388_608:
            raise ValueError("max_bytes must be between 1 and 8388608")
        with (
            python_ast_cache.python_ast_session(),
            syntax_session(self.index.range_provider),
        ):
            return self._bindings_observation(relpath, limit, max_bytes)
