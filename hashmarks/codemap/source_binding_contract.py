"""Bounds for source-local binding observations, never a resolution registry."""

from __future__ import annotations

MAX_ALIAS_DEPTH = 8
MAX_BINDING_NODES = 100_000
MAX_BINDING_RESULTS = 100_000
MAX_BINDING_DETAILS = 256
MAX_LITERAL_BYTES = 256
MAX_HELPER_EDGES = 1
MAX_BINDING_EXPRESSION_DEPTH = 32
MAX_BINDING_SUPPORTING_RANGES = 64
BINDING_INTERPRETER_SIGNATURE = "hashmarks.source-binding-interpreter.v5"
BINDING_FACT_KINDS = (
    "declaration",
    "import-binding",
    "alias-binding",
    "literal-binding",
    "default-binding",
    "argument-binding",
    "conditional-call-binding",
    "reference",
    "call-site",
    "literal-expression",
    "property-write",
    "module-declaration",
    "callable-signature",
)


class BindingObservationBound(ValueError):
    """The complete source scope could not be qualified within its bound."""
