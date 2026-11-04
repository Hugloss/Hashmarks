"""Bounded, explicitly selected Make/shell source declarations and invocations.

This observer recognizes a documented lexical subset. References identify
source candidates, never effective expansion, runtime binding, or execution.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict

from hashmarks.paths import normalize_relative_path

from .make_shell_static_bindings import add_static_binding_observations
from .repository_declaration_contract import MAX_GROUPS
from .repository_declaration_provider import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)

MAX_MAKE_SHELL_PATHS = 16
MAX_MAKE_SHELL_BYTES = 262_144
MAX_STATEMENT_CHARS = 16_384
MAX_STATEMENT_WORDS = 256
MAX_MAKE_SHELL_FACTS = 4_096
_NAME = r"[A-Za-z_][A-Za-z_0-9]*"
_MAKE_NAME = r"[A-Za-z_.][A-Za-z_0-9.-]*"
_ASSIGNMENT = re.compile(rf"^({_NAME})=(.*)$", re.DOTALL)
_MAKE_ASSIGNMENT = re.compile(
    rf"^\s*((?:(?:export|override|private)\s+)*)({_MAKE_NAME})\s*(::=|:=|\?=|\+=|!=|=)\s*(.*)$",
    re.DOTALL,
)
_FUNCTION = re.compile(
    rf"^(?:function\s+)?({_NAME})\s*\(\s*\)\s*\{{\s*(.*)$", re.DOTALL
)
_ARRAY_ASSIGNMENT = re.compile(
    rf"^(?:(local|readonly|export)\s+)?({_NAME})=\((.*)\)\s*$", re.DOTALL
)
_TOKEN = re.compile(
    r"(?:'[^']*'|\"(?:\\.|[^\"\\])*\"|\\.|\$\("
    + _MAKE_NAME
    + r"\)|[^\s;&|<>()'\"\\])+|&&|\|\||[;&|<>()]",
    re.DOTALL,
)
_FRAGMENT = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"|\\.|[^'\"\\]+", re.DOTALL)
_SHELL_REFERENCE = re.compile(
    rf"(?<!\$)\$(?:\{{({_NAME}|[0-9]+|[@*])(?:\[[@*]\]|(?::?-)[^}}]*)?\}}|({_NAME}|[0-9]|[@*]))"
)
_MAKE_REFERENCE = re.compile(rf"(?<!\$)\$(?:\{{({_MAKE_NAME})\}}|\(({_MAKE_NAME})\))")
_SEPARATORS = frozenset({";", "&&", "||", "|", "&"})
_CONTROL_STARTS = frozenset({"if", "for", "while", "until", "case", "select"})
_CONTROL_ENDS = frozenset({"fi", "done", "esac"})
_CONTROL_PARTS = frozenset({"then", "do", "else", "elif", "in"})


@dataclass(frozen=True, slots=True)
class _Line:
    start: int
    end: int
    text: str


@dataclass(slots=True)
class _Fact:
    kind: str
    line: _Line
    context: tuple[str, ...]
    value: dict[str, object]
    references: tuple[str, ...] = ()
    language: str = "shell"


class _Word(TypedDict):
    expression: str
    state: str
    literal: str | None
    reference_names: list[str]
    reference: NotRequired[dict[str, object]]


class _Assignment(TypedDict):
    name: str
    value_expression: _Word


def _quote_context(text: str) -> str:
    quote = ""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif char in {"'", '"'} and (not quote or quote == char):
            quote = "" if quote else char
    return quote


def _logical_lines(source: str, *, language: str) -> Iterator[_Line]:
    pending = ""
    start = 1
    recipe = False
    continued = False
    for number, physical in enumerate(source.splitlines(), 1):
        if not continued:
            start, recipe = number, physical.startswith("\t")
        part = (
            physical[1:]
            if continued and recipe and physical.startswith("\t")
            else physical
        )
        text = pending + part
        if len(text) > MAX_STATEMENT_CHARS:
            raise ValueError("Make/shell statement exceeds character bound")
        trailing = len(text) - len(text.rstrip("\\"))
        if trailing % 2:
            if (language == "shell" or recipe) and _quote_context(text) == "'":
                raise ValueError("multiline single-quoted shell syntax is unsupported")
            pending = text[:-1] + (" " if language == "make" and not recipe else "")
            continued = True
        else:
            yield _Line(start, number, text)
            pending = ""
            continued = False
    if continued:
        raise ValueError("unterminated Make/shell line continuation")


def _tokens(text: str) -> list[str]:
    words: list[str] = []
    offset = 0
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
            continue
        if text[offset] == "#":
            break
        match = _TOKEN.match(text, offset)
        if match is None:
            raise ValueError("unsupported or unterminated Make/shell quoting")
        words.append(match.group())
        offset = match.end()
        if len(words) > MAX_STATEMENT_WORDS:
            raise ValueError("Make/shell statement exceeds word bound")
    return words


def _active_fragments(expression: str, *, language: str) -> tuple[str, str]:
    active: list[str] = []
    unquoted: list[str] = []
    for match in _FRAGMENT.finditer(expression):
        part = match.group()
        if part.startswith("'"):
            if language == "make":
                active.append(part[1:-1])
        elif part.startswith('"'):
            inner = part[1:-1]
            active.append(inner if language == "make" else re.sub(r"\\.", "", inner))
        elif part.startswith("\\"):
            if language == "make":
                active.append(part)
        else:
            active.append(part)
            unquoted.append(part)
    return " ".join(active), " ".join(unquoted)


def _literal_word(expression: str) -> str:
    """Decode the supported quote/escape subset without evaluating expansions."""
    parts: list[str] = []
    for match in _FRAGMENT.finditer(expression):
        part = match.group()
        if part.startswith("'"):
            parts.append(part[1:-1])
        elif part.startswith('"'):
            parts.append(re.sub(r'\\([$`"\\])', r"\1", part[1:-1]))
        elif part.startswith("\\"):
            parts.append(part[1:])
        else:
            parts.append(part)
    return "".join(parts)


def _word(expression: str, *, language: str) -> _Word:
    active, unquoted = _active_fragments(expression, language=language)
    reference_pattern = _MAKE_REFERENCE if language == "make" else _SHELL_REFERENCE
    references = tuple(
        dict.fromkeys(
            match.group(1) or match.group(2)
            for match in reference_pattern.finditer(active)
        )
    )
    unresolved = (
        "$" in active or "`" in active or bool(re.search(r"[*?\[\]{}~]", unquoted))
    )
    result: _Word = {
        "expression": expression,
        "state": "unresolved-expansion" if unresolved else "literal",
        "literal": None if unresolved else _literal_word(expression),
        "reference_names": list(references),
    }
    if language == "shell":
        quoted = expression.startswith('"') and expression.endswith('"')
        selected = expression[1:-1] if quoted else expression
        match = re.fullmatch(
            rf"\$(?:\{{({_NAME}|[0-9]+|[@*])(\[[@*]\])?(?:(:?)-(.*))?\}}|({_NAME}|[0-9]|[@*]))",
            selected,
            re.DOTALL,
        )
        if match is not None:
            name, array, colon, fallback, simple = match.groups()
            name = name or simple
            result["reference"] = {
                "name": name,
                "kind": "array-elements"
                if array
                else "positional"
                if name.isdigit() or name in {"@", "*"}
                else "scalar",
                "quoted": quoted,
                "element_mode": array[1] if array else None,
                "operator": ":-"
                if colon == ":"
                else "-"
                if fallback is not None
                else None,
                "fallback_expression": fallback,
                "effective_value": "not-established",
            }
    else:
        quoted = expression[:1] in {"'", '"'} and expression[-1:] == expression[:1]
        selected = expression[1:-1] if quoted else expression
        match = _MAKE_REFERENCE.fullmatch(selected)
        if match is not None:
            result["reference"] = {
                "name": match.group(1) or match.group(2),
                "kind": "make-variable",
                "quoted": quoted,
                "effective_value": "not-established",
            }
    return result


def _reference_names(words: Sequence[_Word]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(str(name) for word in words for name in word["reference_names"])
    )


def _command_parts(words: Sequence[str]) -> Iterator[tuple[list[str], str]]:
    current: list[str] = []
    preceding = ""
    for word in words:
        if word in _SEPARATORS:
            if current:
                yield current, preceding
            current, preceding = [], word
        else:
            current.append(word)
    if current:
        yield current, preceding


def _environment_prefix(
    tokens: Sequence[str], *, language: str
) -> tuple[list[_Assignment], list[str]]:
    assignments: list[_Assignment] = []
    for token in tokens:
        match = _ASSIGNMENT.fullmatch(token)
        if match is None:
            break
        assignments.append(
            {
                "name": match.group(1),
                "value_expression": _word(match.group(2), language=language),
            }
        )
    return assignments, list(tokens[len(assignments) :])


def _assignment_references(assignments: Sequence[_Assignment]) -> tuple[str, ...]:
    return _reference_names([row["value_expression"] for row in assignments])


@dataclass(slots=True)
class _ShellReader:
    language: str = "shell"
    base_context: tuple[str, ...] = ()
    functions: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    facts: list[_Fact] = field(default_factory=list)
    stopped: bool = False
    max_facts: int = MAX_GROUPS

    @property
    def context(self) -> tuple[str, ...]:
        return (*self.base_context, *self.functions, *self.controls)

    def _record(
        self,
        kind: str,
        line: _Line,
        value: dict[str, object],
        references: tuple[str, ...] = (),
    ) -> None:
        self.facts.append(
            _Fact(kind, line, self.context, value, references, self.language)
        )
        if len(self.facts) > self.max_facts:
            raise ValueError("Make/shell declarations exceed group bound")

    def _control(self, line: _Line, word: str) -> bool:
        if word in _CONTROL_STARTS:
            self._record("shell-control-syntax", line, {"expression": line.text})
            self._loop_binding(line, word)
            self.controls.append(f"conditional-or-loop:{line.start}")
        elif word in _CONTROL_ENDS:
            self._record("shell-control-syntax", line, {"expression": line.text})
            if self.controls:
                self.controls.pop()
        elif word in _CONTROL_PARTS:
            self._record("shell-control-syntax", line, {"expression": line.text})
        else:
            return False
        return True

    def _loop_binding(self, line: _Line, word: str) -> None:
        if word not in {"for", "select"}:
            return
        tokens = _tokens(line.text)
        name = tokens[1] if len(tokens) > 1 else ""
        self._record(
            "shell-binding-write",
            line,
            {
                "name": name if re.fullmatch(_NAME, name) else None,
                "write_syntax": "loop-target",
                "effective_value": "not-established",
            },
        )

    def _function(self, line: _Line) -> bool:
        match = _FUNCTION.fullmatch(line.text.strip())
        if match is None:
            return False
        name, body = match.groups()
        self._record("shell-function-declaration", line, {"name": name})
        self.functions.append(f"function:{name}:{line.start}")
        body_tokens = _tokens(body)
        inline = bool(body_tokens) and body_tokens[-1] == "}"
        body = " ".join(body_tokens[:-1] if inline else body_tokens)
        if body.strip():
            self.read(_Line(line.start, line.end, body))
        if inline:
            self.functions.pop()
        return True

    def _declarations(
        self, line: _Line, tokens: list[str], *, modifier: str = ""
    ) -> bool:
        assignments, remainder = _environment_prefix(tokens, language=self.language)
        if not assignments or remainder:
            return False
        for row in assignments:
            references = _assignment_references([row])
            kind = (
                "shell-alias-declaration"
                if modifier == "alias"
                else "shell-variable-declaration"
            )
            self._record(
                kind,
                line,
                {
                    **row,
                    "assignment_operator": "=",
                    "modifier": modifier,
                    "effective_value": "not-established",
                    "alias_binding": "source-reference-only"
                    if references
                    else "not-established",
                },
                references,
            )
        return True

    def _command(self, line: _Line, tokens: list[str], preceding: str) -> None:
        if tokens[0] in _CONTROL_STARTS | _CONTROL_ENDS | _CONTROL_PARTS:
            self._record(
                "shell-unresolved-statement",
                line,
                {
                    "expression": " ".join(tokens),
                    "reason": "compound-control-not-interpreted",
                },
            )
            return
        modifier = (
            tokens[0] if tokens[0] in {"export", "local", "readonly", "alias"} else ""
        )
        declarations = tokens[1:] if modifier else tokens
        if self._declarations(line, declarations, modifier=modifier):
            return
        assignments, command = _environment_prefix(tokens, language=self.language)
        if command and command[0] in {"shift", "set"}:
            self._record(
                "shell-positional-write",
                line,
                {
                    "operation_spelling": command[0],
                    "native_operation_binding": "not-established",
                    "effective_parameters": "not-established",
                },
            )
        words = [_word(token, language=self.language) for token in command]
        references = (*_assignment_references(assignments), *_reference_names(words))
        self._record(
            "shell-command-expression",
            line,
            {
                "expression": " ".join(tokens),
                "words": words,
                "literal_argv": [word["literal"] for word in words]
                if all(word["state"] == "literal" for word in words)
                else None,
                "command_local_environment": assignments,
                "preceding_operator": preceding,
                "command_binding": "not-established",
                "sourced_file_contents": "not-observed"
                if tokens[0] in {".", "source"}
                else "not-applicable",
            },
            tuple(dict.fromkeys(references)),
        )

    def read(self, line: _Line) -> None:
        text = line.text.strip()
        if self.stopped or not text or text.startswith("#"):
            return
        first = text.split(maxsplit=1)[0].rstrip(";")
        if self._control(line, first) or self._function(line):
            return
        if self._close_function(text):
            return
        if self._array(line, text):
            return
        tokens = _tokens(text)
        if not tokens:
            return
        if self._unsupported(line, tokens):
            return
        for words, preceding in _command_parts(tokens):
            self._command(line, words, preceding)

    def _close_function(self, text: str) -> bool:
        if text not in {"}", "};"}:
            return False
        if self.functions:
            self.functions.pop()
        return True

    def _array(self, line: _Line, text: str) -> bool:
        array = _ARRAY_ASSIGNMENT.fullmatch(text)
        if array is None or self.language != "shell":
            return False
        modifier, name, body = array.groups()
        tokens = _tokens(body)
        if any(token in _SEPARATORS | {"(", ")", "<", ">"} for token in tokens):
            return False
        elements = [_word(token, language=self.language) for token in tokens]
        self._record(
            "shell-array-declaration",
            line,
            {
                "name": name,
                "elements": elements,
                "modifier": modifier or "",
                "assignment_operator": "=",
                "effective_value": "not-established",
            },
            _reference_names(elements),
        )
        return True

    def _unsupported(self, line: _Line, tokens: list[str]) -> bool:
        active, _ = _active_fragments(line.text, language=self.language)
        operators = set(tokens) & {"(", ")", "<", ">", "{", "}"}
        dynamic_control = tokens[0] in {
            "eval",
            "declare",
            "typeset",
            "function",
            "[[",
            "((",
        }
        if not operators and "`" not in active and not dynamic_control:
            return False
        self._record(
            "shell-unresolved-statement",
            line,
            {
                "expression": line.text,
                "token_expressions": list(tokens),
                "reason": "unsupported-control-redirection-or-expansion",
                "remaining_file_observation": "not-observed"
                if "<<" in active
                else "continues",
            },
        )
        # A here-document's following physical lines are data, not commands.
        if "<<" in active:
            self.stopped = True
        elif "`" not in active:
            self._observe_command_prefix(line, tokens)
        return True

    def _observe_command_prefix(self, line: _Line, tokens: list[str]) -> None:
        parts = list(_command_parts(tokens))
        if len(parts) < 2 or parts[1][1] not in {"&&", "||"}:
            return
        words = parts[0][0]
        if words[0] in _CONTROL_STARTS | _CONTROL_ENDS | _CONTROL_PARTS:
            return
        if set(words) & {"(", ")", "<", ">", "{", "}"}:
            return
        self.controls.append(f"uninterpreted-remainder:{line.start}")
        self._command(_Line(line.start, line.end, " ".join(words)), words, "")
        self.controls.pop()
        self.facts[-1].value["prefix_of_uninterpreted_statement"] = True


def _make_comment(text: str) -> str:
    for offset, char in enumerate(text):
        if char == "#":
            prefix = text[:offset]
            escapes = len(prefix) - len(prefix.rstrip("\\"))
            if escapes % 2 == 0:
                return prefix.rstrip()
    return text.rstrip()


@dataclass(slots=True)
class _MakeReader:
    facts: list[_Fact] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    targets: tuple[str, ...] = ()
    define_depth: int = 0
    custom_recipe_prefix: bool = False
    stopped: bool = False
    max_facts: int = MAX_GROUPS

    def _record(
        self,
        kind: str,
        line: _Line,
        value: dict[str, object],
        references: tuple[str, ...] = (),
    ) -> None:
        self.facts.append(
            _Fact(kind, line, tuple(self.conditions), value, references, "make")
        )
        if len(self.facts) > self.max_facts:
            raise ValueError("Make/shell declarations exceed group bound")

    def _directive(self, line: _Line, text: str) -> bool:
        first = text.split(maxsplit=1)[0]
        if first in {"define", "endef"} or self.define_depth:
            self._record(
                "make-unresolved-directive",
                line,
                {"expression": text, "reason": "multiline-macro-not-interpreted"},
            )
            self.define_depth += int(first == "define") - int(
                first == "endef" and self.define_depth > 0
            )
        elif first in {"include", "-include", "sinclude"}:
            self._record(
                "make-include-declaration",
                line,
                {"expression": text, "included_contents": "not-observed"},
            )
        elif first in {"ifdef", "ifndef", "ifeq", "ifneq"}:
            self._record("make-conditional-syntax", line, {"expression": text})
            self.conditions.append(f"make-condition:{line.start}")
        elif first in {"else", "endif"}:
            self._record("make-conditional-syntax", line, {"expression": text})
            if first == "endif" and self.conditions:
                self.conditions.pop()
        else:
            return False
        return True

    def _assignment(self, line: _Line, text: str) -> bool:
        match = _MAKE_ASSIGNMENT.fullmatch(text)
        if match is None:
            return False
        modifiers, name, operator, value = match.groups()
        active, _ = _active_fragments(value, language="make")
        references = tuple(
            dict.fromkeys(
                item.group(1) or item.group(2)
                for item in _MAKE_REFERENCE.finditer(active)
            )
        )
        tokens: list[str] = []
        try:
            tokens = _tokens(value)
        except ValueError:
            words = None
        else:
            words = (
                [_word(token, language="make") for token in tokens]
                if not any(
                    token in _SEPARATORS | {"(", ")", "<", ">"} for token in tokens
                )
                else None
            )
        environment, command = (
            _environment_prefix(tokens, language="make")
            if words is not None
            else ([], [])
        )
        self._record(
            "make-variable-declaration",
            line,
            {
                "name": name,
                "assignment_operator": operator,
                "modifiers": modifiers.split(),
                "value_expression": value,
                "value_words": words,
                "value_environment_prefix": environment,
                "value_command_words": [
                    _word(token, language="make") for token in command
                ]
                if words is not None
                else None,
                "effective_value": "not-established",
                "evaluation": "native-make-owned",
            },
            references,
        )
        if name == ".RECIPEPREFIX":
            self.custom_recipe_prefix = True
        return True

    def _recipe(self, line: _Line) -> None:
        recipe = line.text[1:].lstrip(" \t")
        prefixes = re.match(r"[@+\-]*", recipe)
        prefix = prefixes.group() if prefixes is not None else ""
        if self.custom_recipe_prefix or not self.targets:
            self._record(
                "make-unresolved-recipe",
                line,
                {
                    "expression": line.text,
                    "reason": "custom-recipe-prefix-or-unestablished-target",
                },
            )
            return
        shell = _ShellReader(
            language="make",
            base_context=(*self.conditions, f"make-recipe:{line.start}"),
            max_facts=self.max_facts,
        )
        shell.read(_Line(line.start, line.end, recipe[len(prefix) :]))
        for fact in shell.facts:
            fact.value["make_targets"] = list(self.targets)
            fact.value["recipe_prefixes"] = prefix
        self.facts.extend(shell.facts)
        self.stopped = shell.stopped

    def _target(self, line: _Line, text: str) -> None:
        names, separator, prerequisites = text.partition(":")
        targets = tuple(names.split())
        if not separator or not targets or re.search(r"[$%=&|;{}\\*?\[\]~]", names):
            self._record("make-unresolved-statement", line, {"expression": text})
            self.targets = ()
            return
        self.targets = targets
        self._record(
            "make-target-declaration",
            line,
            {
                "targets": list(targets),
                "prerequisite_expression": prerequisites,
                "effective_prerequisites": "not-established",
            },
        )
        # Inline recipes and target-specific assignments remain source text.
        if ";" in prerequisites or "=" in prerequisites:
            self._record(
                "make-unresolved-statement",
                line,
                {
                    "expression": prerequisites,
                    "reason": "inline-recipe-or-target-specific-assignment-not-interpreted",
                },
            )

    def read(self, line: _Line) -> None:
        text = _make_comment(line.text).strip()
        if not text or self.stopped:
            return
        if self.define_depth:
            self._directive(line, text)
        elif line.text.startswith("\t"):
            self._recipe(line)
        elif not self._directive(line, text) and not self._assignment(line, text):
            self._target(line, text)
        if len(self.facts) > self.max_facts:
            raise ValueError("Make/shell declarations exceed group bound")


def _candidate(fact: _Fact) -> dict[str, object]:
    return {
        "kind": fact.kind,
        "start_line": fact.line.start,
        "end_line": fact.line.end,
        "context": list(fact.context),
        **(
            {"assignment_operator": fact.value["assignment_operator"]}
            if "assignment_operator" in fact.value
            else {}
        ),
    }


def _source_references(fact: _Fact, facts: Sequence[_Fact]) -> dict[str, object]:
    variables = [
        row
        for row in facts
        if row.kind
        in (
            {"make-variable-declaration"}
            if fact.language == "make"
            else {
                "shell-variable-declaration",
                "shell-binding-write",
                "shell-array-declaration",
            }
        )
    ]
    references = [
        {
            "name": name,
            "declaration_candidates": [
                _candidate(row) for row in variables if row.value.get("name") == name
            ],
            "binding": "unresolved",
            "candidate_scope": "same-selected-file-syntax-only",
        }
        for name in fact.references
    ]
    result: dict[str, object] = {"variable_references": references}
    words = fact.value.get("words")
    if not isinstance(words, list) or not words:
        return result
    command = words[0].get("literal")
    if command is not None:
        result["command_declaration_candidates"] = [
            _candidate(row)
            for row in facts
            if row.kind in {"shell-function-declaration", "shell-alias-declaration"}
            and row.value["name"] == command
        ]
    return result


def _source_value(fact: _Fact, facts: Sequence[_Fact]) -> dict[str, object]:
    return {
        **fact.value,
        **_source_references(fact, facts),
        "context": list(fact.context),
        "source_language": fact.language,
        "authority": "direct-static-syntax-only",
        "execution": "not-established",
        "coverage": "incomplete",
        "negative_evidence_admissible": False,
    }


def _group(
    path: str, fact: _Fact, ordinal: int, facts: Sequence[_Fact], *, provider: str
) -> dict[str, object]:
    scope = {"path": path, "line": fact.line.start, "ordinal": ordinal}
    return {
        "group_id": f"{path}:{fact.line.start}:{ordinal}",
        "concept": {"kind": fact.kind},
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {"producer": provider, "reason": "syntax-not-effective-execution"},
        },
        "declarations": [
            {
                "declaration_id": "selected-source-syntax",
                "semantic_role": {"kind": "syntax-only-observation"},
                "value_state": "resolved",
                "value": _source_value(fact, facts),
                "producer": {
                    "provider": provider,
                    "parser": "bounded-make-shell-syntax.v4",
                },
                "evidence": [
                    {
                        "path": path,
                        "start_line": fact.line.start,
                        "end_line": fact.line.end,
                    }
                ],
            }
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "producer": provider,
                "reason": "selected-files-and-supported-syntax-only",
            },
        },
    }


def _file_fact(
    raw: str, facts: Sequence[_Fact], language: str, *, stopped: bool
) -> _Fact:
    return _Fact(
        "make-shell-file-observation",
        _Line(1, max(1, len(raw.splitlines())), ""),
        (),
        {
            "facts": [
                {
                    "kind": fact.kind,
                    "start_line": fact.line.start,
                    "end_line": fact.line.end,
                    "value": _source_value(fact, facts),
                }
                for fact in facts
            ],
            "observed_fact_count": len(facts),
            "facts_completeness": "incomplete"
            if stopped
            else "complete-supported-subset",
            "facts_truncation": "not-truncated",
            "remaining_source": "not-observed" if stopped else "selected-file-observed",
            "max_source_facts": MAX_MAKE_SHELL_FACTS,
            "semantic_coverage": "incomplete",
        },
        language=language,
    )


@dataclass(frozen=True, slots=True)
class MakeShellDeclarations:
    """Observe the documented Make/shell subset in explicitly selected files."""

    make_paths: tuple[str, ...] = ()
    shell_paths: tuple[str, ...] = ()
    name: str = "make-shell-syntax"
    layout: Literal["groups", "file"] = "groups"

    def __post_init__(self) -> None:
        if self.layout not in {"groups", "file"}:
            raise ValueError("Make/shell layout must be groups or file")
        paths = (*self.make_paths, *self.shell_paths)
        if not 1 <= len(paths) <= MAX_MAKE_SHELL_PATHS:
            raise ValueError("Make/shell provider requires 1..16 exact paths")
        if len(set(paths)) != len(paths):
            raise ValueError("Make/shell selections must be unique across languages")
        if any(
            not isinstance(path, str)
            or normalize_relative_path(path, allow_root=False) != path
            for path in paths
        ):
            raise ValueError("Make/shell provider requires canonical repository paths")

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        groups: list[dict[str, object]] = []
        missing: list[str] = []
        selected = {
            **dict.fromkeys(self.make_paths, "make"),
            **dict.fromkeys(self.shell_paths, "shell"),
        }
        for path, language in sorted(selected.items()):
            if not context.exists(path):
                missing.append(path)
                continue
            raw = context.read_bytes(path)
            if len(raw) > MAX_MAKE_SHELL_BYTES:
                raise ValueError("Make/shell source exceeds bounded input")
            max_facts = MAX_MAKE_SHELL_FACTS if self.layout == "file" else MAX_GROUPS
            reader = (
                _MakeReader(max_facts=max_facts)
                if language == "make"
                else _ShellReader(max_facts=max_facts)
            )
            text = raw.decode("utf-8")
            for line in _logical_lines(text, language=language):
                reader.read(line)
            add_static_binding_observations(reader.facts)
            projected = (
                [_file_fact(text, reader.facts, language, stopped=reader.stopped)]
                if self.layout == "file"
                else reader.facts
            )
            groups.extend(
                _group(path, fact, ordinal, reader.facts, provider=self.name)
                for ordinal, fact in enumerate(projected)
            )
            if len(groups) > MAX_GROUPS:
                raise ValueError("Make/shell declarations exceed group bound")
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "semantics": "hashmarks.make-shell-syntax.v4",
                "layout": self.layout,
                "make_paths": sorted(self.make_paths),
                "shell_paths": sorted(self.shell_paths),
                "missing_selected_paths": missing,
                "coverage": "selected-supported-source-syntax-only",
                "semantic_coverage": "incomplete",
                "execution": "not-performed",
                "effective_environment": "not-established",
                "negative_evidence_admissible": False,
            },
        )
