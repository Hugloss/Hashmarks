"""Bounded authored Make/shell candidates over the canonical lexical facts.

Candidates describe selected source forms, not native expansion, an effective
command/environment, or whether a function is invoked. Runtime authority stays
with Make, Bash and the external consumer. Unknown origins never become values.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from .repository_declaration_contract import MAX_PACKET_BYTES, encoded_json_bytes

if TYPE_CHECKING:
    from .make_shell_declarations import _Fact

MAX_BINDING_HOPS = 8
MAX_INVOCATION_CANDIDATES = 64
_SIMPLE_ATOM = re.compile(r"[A-Za-z_0-9./+-]+", re.ASCII)


@dataclass(frozen=True, slots=True)
class _Candidate:
    words: tuple[str, ...]
    declarations: tuple[_Fact, ...] = ()
    conditions: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    environment: tuple[dict[str, object], ...] = ()


def _combine(candidates: Sequence[_Candidate]) -> _Candidate:
    from .make_shell_declarations import MAX_STATEMENT_WORDS

    if sum(len(row.words) for row in candidates) > MAX_STATEMENT_WORDS:
        raise ValueError("Make/shell source candidate exceeds word bound")
    if (
        sum(len(row.declarations) for row in candidates)
        > MAX_STATEMENT_WORDS * MAX_BINDING_HOPS
    ):
        raise ValueError(
            "Make/shell source candidate exceeds supporting declaration bound"
        )
    return _Candidate(
        tuple(word for candidate in candidates for word in candidate.words),
        tuple(row for candidate in candidates for row in candidate.declarations),
        tuple(
            dict.fromkeys(
                condition for row in candidates for condition in row.conditions
            )
        ),
        tuple(dict.fromkeys(feature for row in candidates for feature in row.features)),
        tuple(item for candidate in candidates for item in candidate.environment),
    )


def _functions(fact: _Fact) -> tuple[str, ...]:
    return tuple(part for part in fact.context if part.startswith("function:"))


def _definitions(facts: Sequence[_Fact]) -> dict[str, list[_Fact]]:
    result: dict[str, list[_Fact]] = {}
    for fact in facts:
        if fact.language == "make" and any(
            part.startswith("make-recipe:") for part in fact.context
        ):
            continue
        if fact.kind not in {
            "make-variable-declaration",
            "shell-variable-declaration",
            "shell-array-declaration",
            "shell-binding-write",
        }:
            continue
        name = fact.value.get("name")
        if isinstance(name, str):
            result.setdefault(name, []).append(fact)
    return result


def _native_make_mutator(fact: _Fact) -> bool:
    key = (
        "value_expression" if fact.kind == "make-variable-declaration" else "expression"
    )
    expression = fact.value.get(key)
    return (
        isinstance(expression, str)
        and re.search(r"\$\(\s*(?:eval|file)\b", expression) is not None
    )


def _shell_binding_mutator(fact: _Fact) -> bool:
    words = fact.value.get("words")
    if (
        fact.kind != "shell-command-expression"
        or not isinstance(words, list)
        or not words
    ):
        return False
    first = words[0]
    return isinstance(first, dict) and first.get("literal") in {
        ".",
        "source",
        "eval",
        "declare",
        "typeset",
    }


def _fact_barrier(fact: _Fact) -> str | None:
    if fact.kind == "shell-binding-write" and fact.value.get("name") is None:
        return "unqualified-loop-binding"
    if fact.language == "make" and any(
        part.startswith("make-recipe:") for part in fact.context
    ):
        # Recipe-local shell syntax cannot establish a Make variable's authored
        # value. Its own unresolved statement remains in evidence.
        return (
            "native-make-function-not-interpreted"
            if _native_make_mutator(fact)
            else None
        )
    if fact.kind in {
        "make-include-declaration",
        "make-unresolved-directive",
        "make-unresolved-statement",
        "make-unresolved-recipe",
        "shell-unresolved-statement",
    }:
        return "source-may-change-bindings"
    if fact.kind == "make-variable-declaration" and _native_make_mutator(fact):
        return "native-make-function-not-interpreted"
    if _shell_binding_mutator(fact):
        return "external-or-dynamic-shell-state"
    return None


def _source_barrier(facts: Sequence[_Fact]) -> str | None:
    return next(
        (reason for fact in facts if (reason := _fact_barrier(fact)) is not None), None
    )


def _expression(fact: _Fact) -> str | None:
    value = fact.value.get("value_expression")
    if isinstance(value, str):
        return value
    expression = value.get("expression") if isinstance(value, dict) else None
    return expression if isinstance(expression, str) else None


def _visible_definitions(
    name: str, fact: _Fact, definitions: Mapping[str, list[_Fact]]
) -> list[_Fact]:
    candidates = definitions.get(name, [])
    if fact.language == "make":
        return list(candidates)
    scope = _functions(fact)
    local = [
        row
        for row in candidates
        if _functions(row) == scope and row.value.get("modifier") == "local"
    ]
    if local:
        return [
            row
            for row in candidates
            if _functions(row) == scope
            and (
                row.value.get("modifier") == "local"
                or row.kind == "shell-binding-write"
            )
        ]
    return [
        row
        for row in candidates
        if not _functions(row)
        or _functions(row) == scope
        or row.value.get("modifier") != "local"
    ]


@dataclass(frozen=True, slots=True)
class _BindingContext:
    fact: _Fact
    before: int
    definitions: Mapping[str, list[_Fact]]
    visited: frozenset[str] = frozenset()
    invocation: _Fact | None = None

    def declaration(self, fact: _Fact, name: str) -> _BindingContext:
        scope = _functions(fact)
        return replace(
            self,
            fact=fact,
            before=fact.line.start,
            visited=self.visited | {name},
            invocation=self.invocation
            if scope and scope == _functions(self.fact)
            else None,
        )


def _make_value(
    declaration: _Fact, context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    operator = declaration.value.get("assignment_operator")
    if operator not in {"=", ":=", "::=", "?="} or declaration.value.get("modifiers"):
        return None
    key = "value_command_words" if command_head else "value_words"
    words = declaration.value.get(key)
    if not isinstance(words, list):
        return None
    candidate = _derive_words(words, context, command_head=command_head)
    if candidate is None:
        return None
    conditions, features = (), ()
    if operator == "?=":
        conditions += ("make-variable-not-already-defined",)
        features += ("authored-default",)
    if len(candidate.words) != 1:
        conditions += ("authored-make-word-fragment-only",)
        features += ("make-source-fragment",)
    if any(not _SIMPLE_ATOM.fullmatch(word) for word in candidate.words):
        conditions += ("native-make-shell-word-boundaries-unestablished",)
        features += ("non-atom-make-fragment",)
    environment = (
        declaration.value.get("value_environment_prefix", []) if command_head else []
    )
    environment = cast("list[dict[str, object]]", environment)
    if environment:
        features += ("source-environment-prefix",)
    return _combine(
        (
            _Candidate(
                (),
                conditions=conditions,
                features=features,
                environment=tuple(environment),
            ),
            candidate,
        )
    )


def _array_value(declaration: _Fact, context: _BindingContext) -> _Candidate | None:
    elements = declaration.value.get("elements")
    if not isinstance(elements, list):
        return None
    candidate = _derive_words(elements, context, command_head=False)
    if candidate is None:
        return None
    return _combine(
        (
            _Candidate(
                (),
                conditions=("selected-array-elements-only",),
                features=("array-elements",),
            ),
            candidate,
        )
    )


def _scalar_value(declaration: _Fact, context: _BindingContext) -> _Candidate | None:
    value = declaration.value.get("value_expression")
    if not isinstance(value, dict):
        return None
    candidate = _derive_word(value, context, command_head=False)
    if candidate is not None and any(
        not _SIMPLE_ATOM.fullmatch(word) for word in candidate.words
    ):
        candidate = _combine((_Candidate((), features=("non-atom-scalar",)), candidate))
    return candidate


def _declaration_value(
    declaration: _Fact,
    context: _BindingContext,
    *,
    command_head: bool,
    array_elements: bool,
) -> _Candidate | None:
    if declaration.kind == "make-variable-declaration":
        return _make_value(declaration, context, command_head=command_head)
    if declaration.kind == "shell-array-declaration":
        return _array_value(declaration, context) if array_elements else None
    return None if array_elements else _scalar_value(declaration, context)


def _resolve(
    name: str,
    context: _BindingContext,
    *,
    command_head: bool,
    array_elements: bool = False,
) -> _Candidate | None:
    candidates = _visible_definitions(name, context.fact, context.definitions)
    if (
        name in context.visited
        or len(context.visited) >= MAX_BINDING_HOPS
        or len(candidates) != 1
    ):
        return None
    declaration = candidates[0]
    before = context.before
    if context.invocation is not None and not _functions(declaration):
        before = context.invocation.line.start
    if declaration.line.start >= before:
        return None
    candidate = _declaration_value(
        declaration,
        context.declaration(declaration, name),
        command_head=command_head,
        array_elements=array_elements,
    )
    if candidate is None:
        return None
    conditions = tuple("source-context-applies:" + part for part in declaration.context)
    features = ("scoped-binding",) if declaration.context else ()
    return _combine((_Candidate((), (declaration,), conditions, features), candidate))


def _make_reference(
    word: Mapping[str, object], context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    reference = word.get("reference")
    if not isinstance(reference, dict) or not isinstance(reference.get("name"), str):
        return None
    candidate = _resolve(reference["name"], context, command_head=command_head)
    if candidate is not None and reference.get("quoted") is True:
        candidate = _combine(
            (
                _Candidate(
                    (),
                    conditions=("native-make-shell-quote-boundaries-unestablished",),
                    features=("quoted-make-source-reference",),
                ),
                candidate,
            )
        )
    return candidate


def _fallback(
    reference: Mapping[str, object], context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    from .make_shell_declarations import _word

    name, expression = reference.get("name"), reference.get("fallback_expression")
    if not isinstance(name, str) or not isinstance(expression, str):
        return None
    if name in context.visited or len(context.visited) >= MAX_BINDING_HOPS:
        return None
    nested = replace(context, visited=context.visited | {name})
    candidate = _derive_word(
        _word(expression, language="shell"), nested, command_head=command_head
    )
    if candidate is None:
        return None
    condition = (
        "parameter-unset-or-empty"
        if reference.get("operator") == ":-"
        else "parameter-unset"
    )
    return _combine(
        (
            _Candidate(
                (),
                conditions=(condition, "parameter-present-branch-unobserved"),
                features=("authored-default",),
            ),
            candidate,
        )
    )


def _positional_words(
    name: str, invocation: _Fact
) -> list[Mapping[str, object]] | None:
    words = cast("list[Mapping[str, object]]", invocation.value["words"])[1:]
    if name == "@":
        return words
    if name.isdigit() and len(name) <= 4 and 1 <= int(name) <= len(words):
        return words[int(name) - 1 : int(name)]
    return None


def _positional(
    reference: Mapping[str, object], context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    if context.invocation is None:
        return None
    name = reference.get("name")
    selected = (
        _positional_words(name, context.invocation) if isinstance(name, str) else None
    )
    if selected is None:
        return None
    caller = _BindingContext(
        context.invocation, context.invocation.line.start, context.definitions
    )
    candidate = _derive_words(selected, caller, command_head=command_head)
    if candidate is None:
        return None
    return _combine(
        (
            _Candidate(
                (),
                conditions=(
                    "one-observed-source-invocation-not-all-callers",
                    "native-positional-word-boundaries-unestablished",
                ),
                features=("invocation-argument",),
            ),
            candidate,
        )
    )


def _shell_reference(
    word: Mapping[str, object], context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    reference = word.get("reference")
    if not isinstance(reference, dict) or not isinstance(reference.get("name"), str):
        return None
    if isinstance(reference.get("fallback_expression"), str):
        return _fallback(reference, context, command_head=command_head)
    if reference.get("kind") == "positional":
        return _positional(reference, context, command_head=command_head)
    if reference.get("element_mode") == "*":
        return None
    candidate = _resolve(
        reference["name"],
        context,
        command_head=command_head,
        array_elements=reference.get("kind") == "array-elements",
    )
    if candidate is not None and reference.get("quoted") is not True:
        candidate = _combine(
            (
                _Candidate(
                    (),
                    conditions=("native-shell-word-splitting-unestablished",),
                    features=("unquoted-source-reference",),
                ),
                candidate,
            )
        )
    return candidate


def _derive_word(
    word: Mapping[str, object], context: _BindingContext, *, command_head: bool
) -> _Candidate | None:
    literal = word.get("literal")
    if word.get("state") == "literal" and isinstance(literal, str):
        return _Candidate((literal,))
    if context.fact.language == "make":
        return _make_reference(word, context, command_head=command_head)
    return _shell_reference(word, context, command_head=command_head)


def _derive_words(
    words: Sequence[Mapping[str, object]],
    context: _BindingContext,
    *,
    command_head: bool = True,
) -> _Candidate | None:
    candidates: list[_Candidate] = []
    for index, word in enumerate(words):
        candidate = _derive_word(
            word, context, command_head=command_head and index == 0
        )
        if candidate is None:
            return None
        candidates.append(candidate)
    return _combine(candidates)


def _evidence(facts: Sequence[_Fact]) -> list[dict[str, object]]:
    distinct = {
        (str(fact.value["name"]), fact.line.start, fact.line.end): fact
        for fact in facts
    }
    return [
        {
            "name": name,
            "start_line": start,
            "end_line": end,
            "context": list(fact.context),
            "assignment_operator": fact.value.get("assignment_operator", "="),
            "expression": _expression(fact),
        }
        for (name, start, end), fact in sorted(distinct.items())
    ]


def _observe_command(
    fact: _Fact,
    definitions: Mapping[str, list[_Fact]],
    barrier: str | None,
    *,
    invocation: _Fact | None = None,
) -> dict[str, object]:
    if barrier is not None:
        return {"state": "unclassified", "reason": barrier}
    words = fact.value.get("words")
    if not isinstance(words, list) or not words:
        return {"state": "unclassified", "reason": "no-command-words"}
    candidate = _derive_words(
        words,
        _BindingContext(fact, fact.line.start, definitions, invocation=invocation),
    )
    if candidate is None:
        return {"state": "unclassified", "reason": "unresolved-word-or-binding"}
    if not candidate.declarations and not candidate.features:
        return {"state": "not-needed", "reason": "existing-literal-argv"}
    conditions = (
        *candidate.conditions,
        *("source-context-applies:" + part for part in fact.context),
    )
    broad = bool(
        candidate.features
        or fact.context
        and any(not part.startswith("make-recipe:") for part in fact.context)
    )
    return {
        "state": "conditional-source" if broad else "conditional-static",
        "words": list(candidate.words),
        "supporting_declarations": _evidence(candidate.declarations),
        "command_local_environment": list(candidate.environment),
        "conditions": list(dict.fromkeys(conditions)),
        "source_features": list(candidate.features),
        "assumptions": [
            "single-selected-file",
            "no-external-environment-or-command-line-overrides",
            "no-native-make-or-shell-expansion",
            "authored-word-candidates-only"
            if broad
            else "simple-single-word-indirection-only",
        ],
        "effective_command": "not-established",
        "execution": "not-established",
        "semantic_coverage": "incomplete",
        "negative_evidence_admissible": False,
    }


def _invocation_candidates(
    fact: _Fact,
    facts: Sequence[_Fact],
    definitions: Mapping[str, list[_Fact]],
    barrier: str | None,
) -> dict[str, object] | None:
    scope = _functions(fact)
    if not scope:
        return None
    selected = scope[-1].split(":")
    name, line = selected[1], int(selected[2])
    declarations = [
        row
        for row in facts
        if row.kind == "shell-function-declaration" and row.value.get("name") == name
    ]
    if len(declarations) != 1:
        return {"state": "unclassified", "reason": "ambiguous-function-declaration"}
    callers = []
    for row in facts:
        words = row.value.get("words")
        if (
            row.kind == "shell-command-expression"
            and isinstance(words, list)
            and words
            and words[0].get("literal") == name
        ):
            callers.append(row)
    if len(callers) > MAX_INVOCATION_CANDIDATES:
        return {
            "state": "unclassified",
            "reason": "source-invocation-bound",
            "truncation": "not-returned",
        }
    candidates: list[dict[str, object]] = []
    candidate_bytes = 0
    positional_write = any(
        row.kind == "shell-positional-write" and _functions(row) == scope
        for row in facts
    )
    for caller in callers:
        words = cast("list[Mapping[str, object]]", caller.value["words"])
        candidates.append(
            {
                "invocation_site": {
                    "start_line": caller.line.start,
                    "end_line": caller.line.end,
                    "context": list(caller.context),
                },
                "function_declaration": {"name": name, "start_line": line},
                "arguments": list(words[1:]),
                "observation": _invocation_observation(
                    fact,
                    caller,
                    definitions,
                    barrier,
                    positional_write=positional_write,
                ),
                "execution": "not-established",
            }
        )
        candidate_bytes += encoded_json_bytes(
            candidates[-1], name="source invocation candidate"
        )
        if candidate_bytes > MAX_PACKET_BYTES:
            raise ValueError(
                "Make/shell source invocation evidence exceeds packet bound"
            )
    return {
        "state": "observed-source-invocations",
        "candidates": candidates,
        "max_helper_edges": 1,
        "max_candidates": MAX_INVOCATION_CANDIDATES,
        "semantic_coverage": "incomplete",
        "negative_evidence_admissible": False,
        "execution": "not-established",
    }


def _invocation_observation(
    fact: _Fact,
    caller: _Fact,
    definitions: Mapping[str, list[_Fact]],
    barrier: str | None,
    *,
    positional_write: bool,
) -> dict[str, object]:
    if _functions(fact)[-1] in caller.context:
        return {
            "state": "unclassified",
            "reason": "recursive-helper-edge-not-interpreted",
        }
    if positional_write:
        return {
            "state": "unclassified",
            "reason": "positional-mutation-not-interpreted",
        }
    return _observe_command(fact, definitions, barrier, invocation=caller)


def add_static_binding_observations(facts: Sequence[_Fact]) -> None:
    """Derive bounded source candidates only; never reread or execute source."""
    definitions = _definitions(facts)
    barrier = _source_barrier(facts)
    observation_bytes = 0
    for fact in facts:
        if fact.kind == "shell-command-expression":
            observed = _observe_command(fact, definitions, barrier)
            observation_bytes += encoded_json_bytes(
                observed, name="source binding candidate"
            )
            fact.value["static_binding_observation"] = observed
            invocation = _invocation_candidates(fact, facts, definitions, barrier)
            if invocation is not None:
                observation_bytes += encoded_json_bytes(
                    invocation, name="source invocation evidence"
                )
                fact.value["invocation_binding_observation"] = invocation
            if observation_bytes > MAX_PACKET_BYTES:
                raise ValueError(
                    "Make/shell source binding evidence exceeds packet bound"
                )
