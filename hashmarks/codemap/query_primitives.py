from __future__ import annotations

from functools import lru_cache
import re

from .python_ast import identifier_terms
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


_TASK_STOPWORDS = frozenset("""a an the and or but if then else when where what which who why how does do did is are was were be been being to of in on at by for from with without into through over under between about against during before after above below up down out off again further then once here there all any both each few more most other some such no nor not only own same so than too very can will just should now need needs needed change changes changing include including relevant likely affected affect remains remain untouched first start appropriate instead predict reconsidered responsibility capability file files why local move name area fact facts describe rule rules one two also must would could should may might belongs belong happen happens""".split())

@lru_cache(maxsize=8192)
def _query_terms(query: str) -> tuple[str, ...]:
    """Return immutable normalized query terms with bounded process-local reuse.

    Tokenization is pure. Reusing it avoids rebuilding the same identifier-term
    sets in scoring/reranking inner loops while retaining no repository authority.
    """
    terms: set[str] = set()
    for token in _WORD_RE.findall(query):
        terms.update(identifier_terms(token))
    # Very short terms are usually noise in code retrieval.
    return tuple(sorted((term for term in terms if len(term) >= 2), key=lambda value: (-len(value), value)))

_TASK_GOVERNANCE_CUES = frozenset({
    "owner", "owners", "ownership", "owns", "owned", "authority", "authoritative",
    "belongs", "belong", "boundary", "boundaries", "architectural", "architecture",
    "forbidden", "allowed", "contract", "contracts", "invariant", "invariants",
    "review", "proposal", "should", "must", "never", "responsibility",
})

_TASK_EVIDENCE_FAMILIES: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"privacy", "private", "public", "secret", "secrets", "leak", "leaking", "redact", "redaction", "sanitize", "sanitized"}),
     ("privacy", "security", "confidentiality", "redaction", "exposure")),
    (frozenset({"observe", "observer", "observability", "diagnostic", "diagnostics", "log", "logs", "logging", "metric", "metrics", "status"}),
     ("observability", "diagnostics", "logging", "metrics", "status")),
    (frozenset({"local", "offline", "checkout", "repository", "workspace"}),
     ("local", "offline", "repository", "workspace")),
    (frozenset({"ci", "cd", "pipeline", "release", "delivery", "automation"}),
     ("ci", "cd", "pipeline", "release", "delivery", "automation")),
    (frozenset({"lock", "lockfile", "fingerprint", "hash", "digest", "identity", "provenance"}),
     ("lock", "identity", "fingerprint", "digest", "provenance")),
    (frozenset({"dependency", "dependencies", "package", "packages", "lockfile", "uv", "npm", "pip", "materialize", "materialization", "resolution"}),
     ("dependency", "lockfile", "package", "materialization", "resolution")),
    (frozenset({"browser", "playwright", "chromium", "firefox", "webkit"}),
     ("browser", "playwright", "preflight")),
    (frozenset({"scout", "observer", "readonly", "read_only", "read-only"}),
     ("scout", "observer", "readonly")),
    (frozenset({"snapshot", "snapshots", "content", "workspace", "sandbox"}),
     ("snapshot", "content", "workspace", "sandbox")),
    (frozenset({"retry", "retries", "backoff", "network", "egress"}),
     ("retry", "network", "backoff", "egress")),
    (frozenset({"capacity", "resource", "resources", "headroom", "memory", "cpu", "pressure", "limit", "limits"}),
     ("capacity", "resource", "headroom", "memory", "cpu", "limits")),
)

