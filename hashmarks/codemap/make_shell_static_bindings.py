"""Conservative authored Make/shell binding observations over existing lexical facts.

Never interprets native execution, environment overrides, sourced files, Make
includes, or shell expansion beyond an explicitly selected simple word.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .make_shell_declarations import _Fact

MAX_BINDING_HOPS = 8
_SIMPLE_ATOM = re.compile(r"[A-Za-z_0-9./+-]+", re.ASCII)
_MAKE_REF = re.compile(r"\$\(([A-Za-z_][A-Za-z_0-9]*)\)|\$\{([A-Za-z_][A-Za-z_0-9]*)\}", re.ASCII)
_SHELL_REF = re.compile(r'\$([A-Za-z_][A-Za-z_0-9]*)|\$\{([A-Za-z_][A-Za-z_0-9]*)\}', re.ASCII)


def _definitions(facts: Sequence[_Fact]) -> dict[str, list[_Fact]]:
    result: dict[str, list[_Fact]] = {}
    for fact in facts:
        if fact.kind not in {"make-variable-declaration", "shell-variable-declaration"}:
            continue
        name = fact.value.get("name")
        if isinstance(name, str):
            result.setdefault(name, []).append(fact)
    return result


def _source_barrier(facts: Sequence[_Fact]) -> str | None:
    """Do not infer a closed binding environment from dynamic source syntax."""
    for fact in facts:
        if fact.kind in {
            "make-include-declaration",
            "make-unresolved-directive",
            "make-unresolved-statement",
            "make-unresolved-recipe",
            "shell-unresolved-statement",
            "shell-control-syntax",
            "make-conditional-syntax",
        }:
            return "source-may-change-bindings"
        if fact.kind == "shell-command-expression":
            words = fact.value.get("words")
            if isinstance(words, list) and words:
                first = words[0]
                if isinstance(first, dict) and first.get("literal") in {
                    ".",
                    "source",
                    "eval",
                    "exec",
                    "declare",
                    "typeset",
                }:
                    return "external-or-dynamic-shell-state"
    return None


def _expression(fact: _Fact) -> str | None:
    if fact.context:
        return None
    value = fact.value.get("value_expression")
    if fact.kind == "make-variable-declaration":
        if (
            fact.value.get("assignment_operator") not in {":=", "::=", "="}
            or fact.value.get("modifiers")
        ):
            return None
        return value.strip() if isinstance(value, str) else None
    if fact.value.get("modifier") not in {"", "export"}:
        return None
    expression = value.get("expression") if isinstance(value, dict) else None
    return expression if isinstance(expression, str) else None

def _direct_reference(expression: str, language: str) -> str | None:
    if language == "shell" and expression.startswith('"') and expression.endswith('"'):
        expression = expression[1:-1]
    pattern = _MAKE_REF if language == "make" else _SHELL_REF
    match = pattern.fullmatch(expression)
    return (match.group(1) or match.group(2)) if match else None


def _static_atom(expression: str, language: str) -> str | None:
    if language == "shell" and expression.startswith('"') and expression.endswith('"'):
        expression = expression[1:-1]
    return expression if _SIMPLE_ATOM.fullmatch(expression) else None


def _resolve(
    name: str,
    *,
    before: int,
    definitions: Mapping[str, list[_Fact]],
    language: str,
    visited: frozenset[str] = frozenset(),
) -> tuple[str, tuple[_Fact, ...]] | None:
    candidates = definitions.get(name, [])
    if (
        name in visited
        or len(visited) >= MAX_BINDING_HOPS
        or len(candidates) != 1
    ):
        return None
    fact = candidates[0]
    # Shell assignments expand immediately. Requiring earlier declarations for
    # Make too is deliberately conservative about later recursive definitions.
    expression = _expression(fact) if fact.line.start < before else None
    if expression is None:
        return None
    atom = _static_atom(expression, language)
    if atom is not None:
        return atom, (fact,)
    referent = _direct_reference(expression, language)
    if referent is None:
        return None
    upstream = _resolve(
        referent,
        before=fact.line.start,
        definitions=definitions,
        language=language,
        visited=visited | {name},
    )
    return (upstream[0], (fact, *upstream[1])) if upstream is not None else None

def _command_word(
    word: Mapping[str, object],
    *,
    fact: _Fact,
    definitions: Mapping[str, list[_Fact]],
) -> tuple[str, tuple[_Fact, ...]] | None:
    if word.get("state") == "literal":
        value = word.get("literal")
        return (value, ()) if isinstance(value, str) else None
    expression = word.get("expression")
    if not isinstance(expression, str):
        return None
    name = _direct_reference(expression, fact.language)
    if name is None:
        return None
    return _resolve(
        name, before=fact.line.start, definitions=definitions, language=fact.language
    )


def _evidence(facts: Sequence[_Fact]) -> list[dict[str, object]]:
    distinct: dict[tuple[str, int, int], _Fact] = {
        (str(fact.value["name"]), fact.line.start, fact.line.end): fact
        for fact in facts
    }
    return [
        {
            "name": name,
            "start_line": start,
            "end_line": end,
            "assignment_operator": fact.value.get("assignment_operator", "="),
            "expression": _expression(fact),
        }
        for (name, start, end), fact in sorted(distinct.items())
    ]


def _observe_command(
    fact: _Fact, definitions: Mapping[str, list[_Fact]], barrier: str | None
) -> dict[str, object]:
    reason = barrier
    if reason is None and any(
        not part.startswith("make-recipe:") for part in fact.context
    ):
        reason = "non-top-level-or-conditional"
    if reason is not None:
        return {"state": "unclassified", "reason": reason}
    words = fact.value.get("words")
    if not isinstance(words, list) or not words:
        return {"state": "unclassified", "reason": "no-command-words"}
    rendered: list[str] = []
    declarations: list[_Fact] = []
    for item in words:
        derived = (
            _command_word(
                cast("Mapping[str, object]", item),
                fact=fact,
                definitions=definitions,
            )
            if isinstance(item, dict)
            else None
        )
        if derived is None:
            return {"state": "unclassified", "reason": "unresolved-word-or-binding"}
        rendered.append(derived[0])
        declarations.extend(derived[1])
    if not declarations:
        return {"state": "not-needed", "reason": "existing-literal-argv"}
    return {
        "state": "conditional-static",
        "words": rendered,
        "supporting_declarations": _evidence(declarations),
        "assumptions": [
            "single-selected-file",
            "no-external-environment-or-command-line-overrides",
            "no-native-make-or-shell-expansion",
            "simple-single-word-indirection-only",
        ],
        "effective_command": "not-established",
        "execution": "not-established",
        "semantic_coverage": "incomplete",
        "negative_evidence_admissible": False,
    }


def add_static_binding_observations(facts: Sequence[_Fact]) -> None:
    """Decorate parsed command facts only; never reread or execute source."""
    definitions = _definitions(facts)
    barrier = _source_barrier(facts)
    for fact in facts:
        if fact.kind == "shell-command-expression":
            fact.value["static_binding_observation"] = _observe_command(
                fact, definitions, barrier
            )
