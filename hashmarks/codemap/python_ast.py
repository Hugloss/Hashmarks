from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

from hashmarks import python_ast_cache

from .model import (
    CODEMAP_SCHEMA,
    PYTHON_PARSER,
    PYTHON_SIGNATURE_PREVIEW_BYTES,
    EdgeRecord,
    LexicalRecord,
    ParsedArtifact,
    SymbolRecord,
    allocate_symbol_occurrence,
)
from .python_binding_scope import (
    PythonReferenceVisitor,
    annotated_assignment_expressions,
    annotations_are_deferred,
    definition_time_expressions,
)
from .python_bindings import PythonBindings
from .python_exports import assignment_name_targets, python_import_target
from .source_binding_contract import BindingObservationBound


def estimate_tokens(text: str | bytes) -> int:
    if not text:
        return 0
    # Intentionally tokenizer-independent. Context budgeting needs a stable,
    # cheap estimate; model-specific tokenizers can be adapters later.
    size = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
    return max(1, (size + 3) // 4)


def python_source_byte_lines(source: str | bytes) -> list[bytes]:
    """Match AST universal newlines while preserving Unicode separators and form feeds."""
    raw = source.encode("utf-8") if isinstance(source, str) else source
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")


def python_symbol_bytes(
    lines: list[bytes], start: int, end: int, byte_columns: tuple[int, int] | None
) -> bytes:
    selected = lines[start - 1 : end]
    if byte_columns is not None:
        left, right = byte_columns
        if start == end:
            return selected[0][left:right]
        selected[0] = selected[0][left:]
        selected[-1] = selected[-1][:right]
    return b"\n".join(selected)


def _binding_header(first_line: bytes) -> tuple[str, int]:
    header = first_line.decode("utf-8").strip()
    encoded = header.encode("utf-8")
    cost = estimate_tokens(encoded)
    # Four extra bytes retain at least one complete code point beyond the
    # public prefix. The disclosure owner can prove truncation from byte
    # length alone, and every displayed preview byte comes from source.
    retained = PYTHON_SIGNATURE_PREVIEW_BYTES + 4
    marker = " … [signature truncated]"
    if len(encoded) <= retained + len(marker.encode("utf-8")):
        return header, cost
    return encoded[:retained].decode("utf-8", errors="ignore") + marker, cost


def _declaration_name(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    parameters = getattr(node, "type_params", ())
    if parameters:
        return f"{node.name}[{', '.join(ast.unparse(p) for p in parameters)}]"
    return node.name


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = "" if node.returns is None else f" -> {ast.unparse(node.returns)}"
    signature = f"{prefix} {_declaration_name(node)}({args}){returns}"
    # Preserve the authored stub shape without interpreting decorators or
    # selecting a runtime implementation among repeated declarations.
    match node.body:
        case [ast.Expr(value=ast.Constant(value=value))] if value is Ellipsis:
            return signature + ": ..."
    return signature


def _class_signature(node: ast.ClassDef) -> str:
    bases = [ast.unparse(value) for value in node.bases]
    bases.extend(ast.unparse(keyword) for keyword in node.keywords)
    suffix = "" if not bases else f"({', '.join(bases)})"
    return f"class {_declaration_name(node)}{suffix}"


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _function_signature(node)
    if isinstance(node, ast.ClassDef):
        return _class_signature(node)
    raise TypeError(type(node).__name__)


def _target_name(node: ast.AST, *, computed_receiver: str = "") -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _target_name(node.value, computed_receiver=computed_receiver)
        receiver = left or computed_receiver
        return f"{receiver}.{node.attr}" if receiver else node.attr
    return None


_VALUE_TYPING_FORMS = frozenset({"Annotated", "Literal"})
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_NON_INDENT_BYTE = re.compile(rb"[^ \t\f]")


@dataclass
class _AnnotationTargets:
    tree: ast.Module
    source: str | bytes

    @cached_property
    def _candidate_names(self) -> set[str]:
        """Narrow lexical work; only the source binding can establish a form."""
        names = set(_VALUE_TYPING_FORMS)
        aliases: dict[str, set[str]] = {}
        # Only statements can declare imports or assignment aliases. Avoid a
        # second walk over every expression in ordinary annotated members.
        pending: list[ast.AST] = list(self.tree.body)
        while pending:
            node = pending.pop()
            pending.extend(
                child
                for child in ast.iter_child_nodes(node)
                if isinstance(child, (ast.stmt, ast.ExceptHandler, ast.match_case))
            )
            if isinstance(node, ast.ImportFrom) and node.module in _TYPING_MODULES:
                names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name in _VALUE_TYPING_FORMS
                )
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
                node.value, (ast.Name, ast.Attribute)
            ):
                spelling = (
                    node.value.id
                    if isinstance(node.value, ast.Name)
                    else node.value.attr
                )
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                aliases.setdefault(spelling, set()).update(
                    t.id for t in targets if isinstance(t, ast.Name)
                )
        pending_names = list(names)
        while pending_names:
            new_names = aliases.get(pending_names.pop(), set()) - names
            names.update(new_names)
            pending_names.extend(new_names)
        return names

    @cached_property
    def _bindings(self) -> PythonBindings | None:
        raw = (
            self.source.encode("utf-8") if isinstance(self.source, str) else self.source
        )
        try:
            return PythonBindings(self.tree, raw)
        except BindingObservationBound:
            return None

    def _typing_form(self, value: ast.expr, anchor: ast.Constant | None) -> str | None:
        if not isinstance(value, (ast.Name, ast.Attribute)):
            return None
        name = value.id if isinstance(value, ast.Name) else value.attr
        if name not in self._candidate_names:
            return None
        if self._bindings is None:
            return "unknown"
        scope = self._bindings.syntax.owners[anchor or value]
        binding = self._bindings.resolve(value, scope)
        if binding.qualification != "qualified":
            return "unknown"
        origin = binding.qualified_absolute_import
        if origin and origin[0] in _TYPING_MODULES and len(origin[1]) == 1:
            return origin[1][0]
        return None

    def _type_arguments(
        self, node: ast.Subscript, anchor: ast.Constant | None
    ) -> tuple[ast.AST, ...]:
        form = self._typing_form(node.value, anchor)
        if form in {"Literal", "unknown"}:
            return ()
        if form == "Annotated":
            items = node.slice.elts if isinstance(node.slice, ast.Tuple) else []
            return tuple(items[:1]) if len(items) >= 2 else ()
        return (node.slice,)

    def targets(
        self, node: ast.AST | None, anchor: ast.Constant | None = None
    ) -> tuple[str, ...]:
        if node is None:
            return ()
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, str):
                return ()
            try:
                expression = ast.parse(node.value.strip(), mode="eval").body
            except (SyntaxError, ValueError, RecursionError):
                return ()
            container = anchor or node
            # Decoded expression coordinates cannot qualify source binding order.
            PythonBindings.locate_annotation_reference(expression, container)
            return self.targets(expression, container)
        target = _target_name(node)
        if target is not None:
            return (target,)
        children: Iterable[ast.AST] = ast.iter_child_nodes(node)
        if isinstance(node, ast.Subscript):
            children = (node.value, *self._type_arguments(node, anchor))
        names = (name for child in children for name in self.targets(child, anchor))
        return tuple(dict.fromkeys(names))


@dataclass
class _Collector(PythonReferenceVisitor):
    lines: list[bytes]
    annotations: _AnnotationTargets

    def __post_init__(self) -> None:
        self.deferred_annotations = annotations_are_deferred(self.annotations.tree)
        self.symbols: list[SymbolRecord] = []
        self.edges: list[EdgeRecord] = []
        self.stack: list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = []
        self.occurrences: set[str] = set()
        self.source_occurrence: str | None = None

    @property
    def current(self) -> str | None:
        return ".".join(node.name for node in self.stack) if self.stack else None

    def _symbol_record(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        kind: str,
        qualname: str,
        signature: str,
        span: tuple[int, int],
    ) -> SymbolRecord:
        start, end = span
        body = python_symbol_bytes(self.lines, start, end, None)
        return SymbolRecord(
            name=node.name,
            qualname=qualname,
            kind=kind,
            signature=signature,
            start_line=start,
            end_line=end,
            signature_tokens=estimate_tokens(signature),
            body_tokens=estimate_tokens(body),
            parent=self.source_occurrence,
        )

    def _function_annotation_edges(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, start: int
    ) -> None:
        for target in self.annotations.targets(node.returns):
            self.edges.append(
                EdgeRecord(qualname, "return-type", target, start, "annotation")
            )
        positional = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        positional.extend(
            arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None
        )
        for arg in positional:
            line = int(getattr(arg, "lineno", start))
            for target in self.annotations.targets(arg.annotation):
                self.edges.append(
                    EdgeRecord(qualname, "parameter-type", target, line, "annotation")
                )

    def _annotation_edges(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        qualname: str,
        start: int,
    ) -> None:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                for target in self.annotations.targets(base):
                    self.edges.append(
                        EdgeRecord(qualname, "inherits", target, start, "annotation")
                    )
        else:
            self._function_annotation_edges(node, qualname, start)

    def _symbol(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, kind: str
    ) -> None:
        parent = self.current
        qualname = node.name if parent is None else f"{parent}.{node.name}"
        signature = _signature(node)
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        occurrence = allocate_symbol_occurrence(self.occurrences, qualname, start)
        self.symbols.append(
            self._symbol_record(node, kind, occurrence, signature, (start, end))
        )
        self._annotation_edges(node, occurrence, start)
        # Definition expressions belong to the surrounding scope. A decorator,
        # default or base expression is not a call made by the declared body.
        for expression in definition_time_expressions(
            node, deferred=self.deferred_annotations
        ):
            self.visit(expression)
        self.stack.append(node)
        previous = self.source_occurrence
        self.source_occurrence = occurrence
        for statement in node.body:
            self.visit(statement)
        self.source_occurrence = previous
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent = self.stack[-1] if self.stack else None
        self._symbol(node, "method" if isinstance(parent, ast.ClassDef) else "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(
                EdgeRecord(
                    self.source_occurrence, "import", alias.name, int(node.lineno)
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            target = python_import_target(node, alias.name)
            self.edges.append(
                EdgeRecord(self.source_occurrence, "import", target, int(node.lineno))
            )
        self.generic_visit(node)

    def _module_bindings(
        self, node: ast.stmt, targets: Iterable[ast.expr], kind: str
    ) -> None:
        if (
            self.current is not None
            or node.end_lineno is None
            or node.end_col_offset is None
        ):
            return
        named = [
            (item, item is root)
            for root in targets
            for item in assignment_name_targets(root)
        ]
        if not named:
            return
        start, end = node.lineno, node.end_lineno
        left, right = node.col_offset, node.end_col_offset
        # Keep ordinary line excerpts (including their comments/indentation).
        # A shared line needs the exact AST statement's UTF-8 byte columns.
        prefix = _NON_INDENT_BYTE.search(self.lines[start - 1], 0, left)
        suffix = _NON_INDENT_BYTE.search(self.lines[end - 1], right)
        columns = (left, right) if prefix or (suffix and suffix[0] == b";") else None
        body = python_symbol_bytes(self.lines, start, end, columns)
        header, header_tokens = _binding_header(body.partition(b"\n")[0])
        body_tokens = estimate_tokens(body)
        for item, direct in named:
            # Each unpacked name is observable; its individual value is not.
            # Keep a compact target spelling and share the defining statement.
            signature = (
                header
                if direct
                else self.lines[item.lineno - 1][
                    item.col_offset : item.end_col_offset
                ].decode("utf-8")
            )
            self.symbols.append(
                SymbolRecord(
                    name=item.id,
                    qualname=allocate_symbol_occurrence(
                        self.occurrences, item.id, start
                    ),
                    kind=kind,
                    signature=signature,
                    start_line=start,
                    end_line=end,
                    signature_tokens=header_tokens
                    if direct
                    else estimate_tokens(signature),
                    body_tokens=body_tokens,
                    start_byte_column=columns[0] if columns else None,
                    end_byte_column=columns[1] if columns else None,
                )
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        self._module_bindings(node, node.targets, "binding")
        self.generic_visit(node)

    def visit_TypeAlias(self, node: ast.stmt) -> None:
        name = getattr(node, "name", None)
        if isinstance(name, ast.Name):
            self._module_bindings(node, (name,), "type")
        # Creating the alias binds its name; its parameters and value are lazy.

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            self._module_bindings(node, (node.target,), "binding")
        for target in self.annotations.targets(node.annotation):
            self.edges.append(
                EdgeRecord(
                    self.source_occurrence,
                    "attribute-type",
                    target,
                    int(node.lineno),
                    "annotation",
                )
            )
        scope = self.stack[-1] if self.stack else self.annotations.tree
        for expression in annotated_assignment_expressions(
            node, scope, deferred=self.deferred_annotations
        ):
            self.visit(expression)

    def visit_Call(self, node: ast.Call) -> None:
        # A computed receiver cannot establish a same-named bare function.
        # Keep its named suffix without indexing arbitrary receiver source.
        target = _target_name(node.func, computed_receiver="<expression>")
        if target:
            self.edges.append(
                EdgeRecord(
                    self.source_occurrence,
                    "call",
                    target,
                    int(node.lineno),
                    "static-name",
                )
            )
        self.generic_visit(node)


def python_parser_signature() -> str:
    """Bind structural artifacts to both projection and native Python grammar."""
    return f"{PYTHON_PARSER}+{python_ast_cache.python_ast_signature()}"


def artifact_key(file_digest: str) -> str:
    payload = json.dumps(
        {
            "schema": CODEMAP_SCHEMA,
            "parser": python_parser_signature(),
            "file_digest": file_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"hashmarks.codemap-artifact.v1\0" + payload).hexdigest()


def identifier_terms(value: str) -> tuple[str, ...]:
    """Stable lexical terms for source identifiers and task queries.

    Keep the full lowercase token while also exposing snake_case and CamelCase
    components.  This lets a task mentioning ``PlanResolver`` narrow a file
    containing ``FleetPlanResolver`` without a repository-wide substring scan.
    """
    import re

    raw = value.strip()
    if not raw:
        return ()
    terms = {raw.lower()}
    for piece in raw.replace("-", "_").split("_"):
        if not piece:
            continue
        parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", piece)
        if not parts:
            parts = [piece]
        for part in parts:
            lowered = part.lower()
            if len(lowered) >= 2:
                terms.add(lowered)
    return tuple(sorted(terms))


def lexical_records(source: str) -> tuple[LexicalRecord, ...]:
    import re

    records: list[LexicalRecord] = []
    for line_no, line in enumerate(source.split("\n"), 1):
        # Deduplicate within one line. The index is for narrowing candidate
        # lines, not term frequency/scoring.
        tokens: set[str] = set()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", line):
            tokens.update(identifier_terms(token))
        records.extend(
            LexicalRecord(token=token, line=line_no) for token in sorted(tokens)
        )
    return tuple(records)


def parse_python(source: str | bytes, *, file_digest: str) -> ParsedArtifact:
    key = artifact_key(file_digest)
    signature = python_parser_signature()
    text = (
        source.decode("utf-8", errors="replace")
        if isinstance(source, bytes)
        else source
    )
    try:
        tree = python_ast_cache.parse_python_ast(source)
    except (SyntaxError, ValueError) as exc:
        return ParsedArtifact(
            artifact_key=key,
            file_digest=file_digest,
            language="python",
            parser=signature,
            full_tokens=estimate_tokens(text),
            outline="",
            lexical=lexical_records(text),
            parse_error=(
                python_ast_cache.UNQUALIFIED_SOURCE_ENCODING
                if isinstance(
                    exc, (python_ast_cache.PythonSourceEncodingError, UnicodeError)
                )
                else f"{type(exc).__name__}: {exc}"
            ),
        )
    collector = _Collector(
        python_source_byte_lines(source), _AnnotationTargets(tree, source)
    )
    collector.visit(tree)
    outline_lines: list[str] = []
    for symbol in collector.symbols:
        depth = symbol.qualname.count(".")
        outline_lines.append(
            f"{'  ' * depth}{symbol.signature}  [{symbol.start_line}-{symbol.end_line}]"
        )
    return ParsedArtifact(
        artifact_key=key,
        file_digest=file_digest,
        language="python",
        parser=signature,
        full_tokens=estimate_tokens(text),
        outline="\n".join(outline_lines),
        symbols=tuple(collector.symbols),
        edges=tuple(collector.edges),
        lexical=lexical_records(text),
    )
