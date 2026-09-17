from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass

from .model import CODEMAP_SCHEMA, EdgeRecord, LexicalRecord, PYTHON_PARSER, ParsedArtifact, SymbolRecord


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Intentionally tokenizer-independent. Context budgeting needs a stable,
    # cheap estimate; model-specific tokenizers can be adapters later.
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = "" if node.returns is None else f" -> {ast.unparse(node.returns)}"
    return f"{prefix} {node.name}({args}){returns}"


def _class_signature(node: ast.ClassDef) -> str:
    bases = [ast.unparse(value) for value in node.bases]
    bases.extend(f"{kw.arg}={ast.unparse(kw.value)}" for kw in node.keywords if kw.arg)
    suffix = "" if not bases else f"({', '.join(bases)})"
    return f"class {node.name}{suffix}"


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _function_signature(node)
    if isinstance(node, ast.ClassDef):
        return _class_signature(node)
    raise TypeError(type(node).__name__)


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _target_name(node.value)
        return node.attr if left is None else f"{left}.{node.attr}"
    return None


def _string_annotation_targets(value: str) -> tuple[str, ...]:
    try:
        return _annotation_targets(ast.parse(value, mode="eval").body)
    except (SyntaxError, ValueError):
        stripped = value.strip()
        return (stripped,) if stripped and all(part.isidentifier() for part in stripped.split(".")) else ()


def _iterable_annotation_targets(nodes) -> tuple[str, ...]:
    return tuple(value for node in nodes for value in _annotation_targets(node))


def _compound_annotation_targets(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Subscript):
        values = (*_annotation_targets(node.value), *_annotation_targets(node.slice))
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        values = (*_annotation_targets(node.left), *_annotation_targets(node.right))
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = _iterable_annotation_targets(node.elts)
    else:
        values = _iterable_annotation_targets(ast.iter_child_nodes(node))
    return tuple(dict.fromkeys(values))


def _annotation_targets(node: ast.AST | None) -> tuple[str, ...]:
    """Return stable named references contained in a type annotation."""
    if node is None:
        return ()
    if isinstance(node, ast.Constant):
        return _string_annotation_targets(node.value) if isinstance(node.value, str) else ()
    target = _target_name(node)
    return (target,) if target is not None else _compound_annotation_targets(node)


@dataclass
class _Collector(ast.NodeVisitor):
    source: str

    def __post_init__(self) -> None:
        self.symbols: list[SymbolRecord] = []
        self.edges: list[EdgeRecord] = []
        self.stack: list[str] = []

    @property
    def current(self) -> str | None:
        return ".".join(self.stack) if self.stack else None

    def _symbol_record(self,node,kind,qualname,signature,span)->SymbolRecord:
        start,end=span
        body = "\n".join(self.source.splitlines()[start - 1 : end])
        return SymbolRecord(
            name=node.name,qualname=qualname,kind=kind,signature=signature,
            start_line=start,end_line=end,signature_tokens=estimate_tokens(signature),
            body_tokens=estimate_tokens(body),parent=self.current,
        )

    def _function_annotation_edges(self,node,qualname,start)->None:
        for target in _annotation_targets(node.returns):
            self.edges.append(EdgeRecord(qualname,"return-type",target,start,"annotation"))
        positional=[*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs]
        positional.extend(arg for arg in (node.args.vararg,node.args.kwarg) if arg is not None)
        for arg in positional:
            line=int(getattr(arg,"lineno",start))
            for target in _annotation_targets(arg.annotation):
                self.edges.append(EdgeRecord(qualname,"parameter-type",target,line,"annotation"))

    def _annotation_edges(self,node,qualname,start)->None:
        if isinstance(node,ast.ClassDef):
            for base in node.bases:
                for target in _annotation_targets(base):
                    self.edges.append(EdgeRecord(qualname,"inherits",target,start,"annotation"))
        else:
            self._function_annotation_edges(node,qualname,start)

    def _symbol(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, kind: str) -> None:
        parent=self.current
        qualname=node.name if parent is None else f"{parent}.{node.name}"
        signature=_signature(node)
        start=int(getattr(node,"lineno",1)); end=int(getattr(node,"end_lineno",start))
        self.symbols.append(self._symbol_record(node,kind,qualname,signature,(start,end)))
        self._annotation_edges(node,qualname,start)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbol(node, "method" if self.stack else "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._symbol(node, "method" if self.stack else "function")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(EdgeRecord(self.current, "import", alias.name, int(node.lineno)))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * int(node.level) + (node.module or "")
        for alias in node.names:
            target = f"{prefix}.{alias.name}" if prefix else alias.name
            self.edges.append(EdgeRecord(self.current, "import", target, int(node.lineno)))
        self.generic_visit(node)


    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for target in _annotation_targets(node.annotation):
            self.edges.append(EdgeRecord(self.current, "attribute-type", target, int(node.lineno), "annotation"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = _target_name(node.func)
        if target:
            self.edges.append(EdgeRecord(self.current, "call", target, int(node.lineno), "static-name"))
        self.generic_visit(node)


def artifact_key(file_digest: str) -> str:
    payload = json.dumps(
        {"schema": CODEMAP_SCHEMA, "parser": PYTHON_PARSER, "file_digest": file_digest},
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
    for line_no, line in enumerate(source.splitlines(), 1):
        # Deduplicate within one line. The index is for narrowing candidate
        # lines, not term frequency/scoring.
        tokens: set[str] = set()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", line):
            tokens.update(identifier_terms(token))
        records.extend(LexicalRecord(token=token, line=line_no) for token in sorted(tokens))
    return tuple(records)


def parse_python(source: str, *, file_digest: str) -> ParsedArtifact:
    key = artifact_key(file_digest)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return ParsedArtifact(
            artifact_key=key,
            file_digest=file_digest,
            language="python",
            parser=PYTHON_PARSER,
            full_tokens=estimate_tokens(source),
            outline="",
            lexical=lexical_records(source),
            parse_error=f"{type(exc).__name__}: {exc}",
        )
    collector = _Collector(source)
    collector.visit(tree)
    outline_lines: list[str] = []
    for symbol in collector.symbols:
        depth = symbol.qualname.count(".")
        outline_lines.append(f"{'  ' * depth}{symbol.signature}  [{symbol.start_line}-{symbol.end_line}]")
    return ParsedArtifact(
        artifact_key=key,
        file_digest=file_digest,
        language="python",
        parser=PYTHON_PARSER,
        full_tokens=estimate_tokens(source),
        outline="\n".join(outline_lines),
        symbols=tuple(collector.symbols),
        edges=tuple(collector.edges),
        lexical=lexical_records(source),
    )
