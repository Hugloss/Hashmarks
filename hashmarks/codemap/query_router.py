from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .repository_domains import RepositoryDomain


class QueryIntent(str, Enum):
    IDENTIFIER = "identifier"
    PATH = "path"
    RELATIONSHIP = "relationship"
    CONFIG = "config"
    TEST = "test"
    STRUCTURAL = "structural"
    CONCEPTUAL = "conceptual"
    HYBRID = "hybrid"


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
_PATHISH = re.compile(
    r"(?:^|\s)(?:\.?[\w.-]+/)+[\w./-]+|\b[\w.-]+\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|kt|c|h|cc|cpp|hpp|cs|rb|php|swift|toml|ya?ml|json|ini|cfg|conf|md)\b",
    re.I,
)
_RELATIONSHIP = {
    "caller",
    "callers",
    "calls",
    "called",
    "reference",
    "references",
    "refs",
    "import",
    "imports",
    "imported",
    "depend",
    "depends",
    "dependency",
    "dependencies",
    "dependent",
    "dependents",
    "uses",
    "usage",
}
_CONFIG = {
    "config",
    "configuration",
    "manifest",
    "makefile",
    "dockerfile",
    "pyproject",
    "package",
    "lockfile",
    "yaml",
    "yml",
    "toml",
    "json",
    "ini",
    "setting",
    "settings",
    "env",
}
_TEST = {
    "test",
    "tests",
    "testing",
    "pytest",
    "vitest",
    "jest",
    "spec",
    "specs",
    "fixture",
    "fixtures",
    "coverage",
}
_STRUCTURAL = {
    "class",
    "function",
    "method",
    "struct",
    "interface",
    "enum",
    "signature",
    "definition",
    "definitions",
    "symbol",
    "symbols",
    "export",
    "exports",
}
_CONCEPTUAL = {
    "architecture",
    "flow",
    "lifecycle",
    "authority",
    "ownership",
    "orchestration",
    "pipeline",
    "how",
    "where",
    "why",
    "design",
    "boundary",
    "boundaries",
    "overview",
}
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


_DOMAIN_WORDS: tuple[tuple[RepositoryDomain, frozenset[str]], ...] = (
    (
        RepositoryDomain.OWNERSHIP,
        frozenset(
            {
                "owner",
                "owners",
                "ownership",
                "owns",
                "owned",
                "authority",
                "authoritative",
                "responsibility",
                "responsibilities",
                "responsible",
                "governs",
                "governed",
                "allowed",
                "forbidden",
            }
        ),
    ),
    (
        RepositoryDomain.ARCHITECTURE,
        frozenset(
            {
                "architecture",
                "architectural",
                "design",
                "boundary",
                "boundaries",
                "structure",
                "structural",
                "shape",
                "layer",
                "layers",
            }
        ),
    ),
    (
        RepositoryDomain.BUILD,
        frozenset(
            {
                "build",
                "make",
                "makefile",
                "init",
                "setup",
                "bootstrap",
                "package",
                "packaging",
                "release",
            }
        ),
    ),
    (
        RepositoryDomain.PLAN,
        frozenset(
            {
                "plan",
                "plans",
                "goon",
                "goons",
                "template",
                "templates",
                "orchestration",
                "pipeline",
            }
        ),
    ),
    (
        RepositoryDomain.CONFIG,
        frozenset(
            {
                "config",
                "configuration",
                "manifest",
                "setting",
                "settings",
                "yaml",
                "yml",
                "toml",
                "json",
                "env",
                "lockfile",
            }
        ),
    ),
    (
        RepositoryDomain.SCRIPT,
        frozenset({"script", "scripts", "shell", "bash", "command", "commands"}),
    ),
    (
        RepositoryDomain.CONTRACT,
        frozenset(
            {
                "contract",
                "contracts",
                "schema",
                "schemas",
                "invariant",
                "invariants",
                "policy",
                "policies",
                "requirement",
                "requirements",
                "allowed",
                "forbidden",
                "valid",
                "invalid",
                "rule",
                "rules",
            }
        ),
    ),
    (
        RepositoryDomain.DOC,
        frozenset({"doc", "docs", "documentation", "readme", "guide"}),
    ),
    (
        RepositoryDomain.TEST,
        frozenset(
            {
                "test",
                "tests",
                "testing",
                "pytest",
                "vitest",
                "jest",
                "spec",
                "fixture",
                "coverage",
            }
        ),
    ),
    (
        RepositoryDomain.SOURCE,
        frozenset(
            {
                "class",
                "function",
                "method",
                "symbol",
                "implementation",
                "code",
                "source",
            }
        ),
    ),
)


def _preferred_domains(words: set[str]) -> tuple[RepositoryDomain, ...]:
    result: list[RepositoryDomain] = []
    for domain, vocabulary in _DOMAIN_WORDS:
        if words & vocabulary and domain not in result:
            result.append(domain)
    # Lifecycle/change-impact/counterfactual questions usually require both the
    # implementation and its governing architecture/contract surface.
    if words & {
        "lifecycle",
        "state",
        "terminal",
        "cancel",
        "cancellation",
        "change",
        "changes",
        "changed",
        "break",
        "breaks",
        "impact",
        "happen",
        "happens",
        "if",
    }:
        for domain in (
            RepositoryDomain.SOURCE,
            RepositoryDomain.ARCHITECTURE,
            RepositoryDomain.CONTRACT,
        ):
            if domain not in result:
                result.append(domain)
    return tuple(result)


@dataclass(frozen=True)
class QueryRoute:
    intent: QueryIntent
    confidence: str
    native_definitions: bool
    caller_expansion: bool
    path_lookup: bool
    lexical_lookup: bool
    reason: str
    preferred_domains: tuple[RepositoryDomain, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "hashmarks.codemap-query-route.v1",
            "intent": self.intent.value,
            "confidence": self.confidence,
            "native_definitions": self.native_definitions,
            "caller_expansion": self.caller_expansion,
            "path_lookup": self.path_lookup,
            "lexical_lookup": self.lexical_lookup,
            "reason": self.reason,
            "preferred_domains": [domain.value for domain in self.preferred_domains],
        }


def _required_query_text(query: str) -> str:
    raw = query.strip()
    if not raw:
        raise ValueError("query must not be empty")
    return raw


def route_query(query: str) -> QueryRoute:
    raw = _required_query_text(query)
    words = {value.lower() for value in _TOKEN.findall(raw)}
    preferred_domains = _preferred_domains(words)

    # Explicit filenames/paths are the strongest signal. Native semantic
    # definitions add little for these and are safe to omit; lexical/path
    # indexes still provide the normal hybrid recall floor.
    if _PATHISH.search(raw):
        intent, confidence, native, reason = (
            QueryIntent.PATH,
            "high",
            False,
            "explicit path or filename",
        )
    elif words & _CONFIG:
        intent, confidence, native, reason = (
            QueryIntent.CONFIG,
            "high",
            False,
            "configuration vocabulary",
        )
    elif words & _TEST:
        intent, confidence, native, reason = (
            QueryIntent.TEST,
            "high",
            False,
            "test vocabulary",
        )
    elif words & _RELATIONSHIP:
        intent, confidence, native, reason = (
            QueryIntent.RELATIONSHIP,
            "high",
            True,
            "relationship vocabulary",
        )
    elif words & _STRUCTURAL:
        intent, confidence, native, reason = (
            QueryIntent.STRUCTURAL,
            "medium",
            True,
            "structural vocabulary",
        )
    elif _IDENTIFIER.fullmatch(raw):
        intent, confidence, native, reason = (
            QueryIntent.IDENTIFIER,
            "high",
            True,
            "exact identifier shape",
        )
    elif words & _CONCEPTUAL:
        intent, confidence, native, reason = (
            QueryIntent.CONCEPTUAL,
            "medium",
            True,
            "conceptual/architecture vocabulary",
        )
    else:
        intent, confidence, native, reason = (
            QueryIntent.HYBRID,
            "low",
            True,
            "ambiguous query keeps full hybrid retrieval",
        )
    return QueryRoute(
        intent,
        confidence,
        native,
        native,
        True,
        True,
        reason,
        preferred_domains,
    )
