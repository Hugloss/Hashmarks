from __future__ import annotations

import fnmatch
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .model import EvidenceVisibility

_SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "**/*.pem",
    "*.key",
    "**/*.key",
    "*.p12",
    "**/*.p12",
    "*.pfx",
    "**/*.pfx",
    ".npmrc",
    "**/.npmrc",
    ".pypirc",
    "**/.pypirc",
    "id_rsa",
    "**/id_rsa",
    "id_ed25519",
    "**/id_ed25519",
)

_SECRET_BASENAMES = frozenset({".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"})
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


@dataclass(frozen=True)
class PolicyDecision:
    index: bool = True
    evidence_visibility: EvidenceVisibility = EvidenceVisibility.SOURCE
    reason: str | None = None


@dataclass(frozen=True)
class _Rule:
    pattern: str
    index: bool | None = None
    visibility: EvidenceVisibility | None = None


class ContextPolicy:
    """Separate CodeMap indexing authority from repository-evidence disclosure authority."""

    def __init__(self, rules: tuple[_Rule, ...] = ()) -> None:
        self.rules = rules

    @classmethod
    def load(cls, workspace: Path, path: Path | None = None) -> ContextPolicy:
        config = workspace / ".hashmarks-context.toml" if path is None else path
        if not config.exists():
            return cls()
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        raw_rules = data.get("rule", [])
        if not isinstance(raw_rules, list):
            raise ValueError(".hashmarks-context.toml: [[rule]] must be an array")
        rules: list[_Rule] = []
        for idx, raw in enumerate(raw_rules):
            if not isinstance(raw, dict) or not isinstance(raw.get("pattern"), str):
                raise ValueError(
                    f".hashmarks-context.toml: rule {idx} needs a string pattern"
                )
            index = raw.get("index")
            if index is not None and not isinstance(index, bool):
                raise ValueError(
                    f".hashmarks-context.toml: rule {idx} index must be boolean"
                )
            visibility_raw = raw.get("visibility")
            visibility = (
                None
                if visibility_raw is None
                else EvidenceVisibility(str(visibility_raw))
            )
            rules.append(
                _Rule(pattern=raw["pattern"], index=index, visibility=visibility)
            )
        return cls(tuple(rules))

    @staticmethod
    def _matches(pattern: str, relpath: str) -> bool:
        return fnmatch.fnmatchcase(relpath, pattern) or Path(relpath).match(pattern)

    @staticmethod
    def _is_builtin_secret_path(relpath: str) -> bool:
        """Equivalent fast path for the fixed built-in secret pattern set."""
        basename = relpath.rsplit("/", 1)[-1]
        return (
            basename in _SECRET_BASENAMES
            or basename.startswith(".env.")
            or basename.endswith(_SECRET_SUFFIXES)
        )

    def fingerprint(self) -> str:
        payload = {
            "schema": "hashmarks.context-policy.v2",
            "builtin_secret_patterns": list(_SECRET_PATTERNS),
            "rules": [
                {
                    "pattern": rule.pattern,
                    "index": rule.index,
                    "visibility": None
                    if rule.visibility is None
                    else rule.visibility.value,
                }
                for rule in self.rules
            ],
        }
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(data).hexdigest()

    def decide(self, relpath: str) -> PolicyDecision:
        path = relpath.replace("\\", "/")
        if self._is_builtin_secret_path(path):
            return PolicyDecision(
                index=False,
                evidence_visibility=EvidenceVisibility.DENY,
                reason="secret-like path",
            )

        decision = PolicyDecision()
        for rule in self.rules:
            if not self._matches(rule.pattern, path):
                continue
            decision = PolicyDecision(
                index=decision.index if rule.index is None else rule.index,
                evidence_visibility=decision.evidence_visibility
                if rule.visibility is None
                else rule.visibility,
                reason=f"context policy: {rule.pattern}",
            )
        if not decision.index:
            return PolicyDecision(
                index=False,
                evidence_visibility=EvidenceVisibility.DENY,
                reason=decision.reason,
            )
        return decision
