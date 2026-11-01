"""Request-local asset consumers composed from maintained source evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, cast

from .asset_reference_syntax import asset_references
from .python_ast import lexical_records
from .repository_domains import classify_repository_path
from .repository_observation import evidence_identity
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification

_ASSET_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".ico",
        ".svg",
        ".pdf",
        ".zip",
        ".gz",
        ".mp4",
        ".webm",
        ".mov",
        ".mp3",
        ".wav",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".bin",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".parquet",
        ".pkl",
        ".pickle",
        ".safetensors",
        ".onnx",
        ".pt",
    }
)


def _asset_candidate(path: str, content: Mapping[str, object]) -> bool:
    return (
        PurePosixPath(path).suffix.lower() in _ASSET_SUFFIXES
        or content.get("kind") in {"binary", "lfs-pointer"}
        or content.get("lfs") is not None
    )


@dataclass(slots=True)
class _AssetConsumers:
    """One request's bounded observation ledger; never retained index state."""

    members: list[dict[str, object]]
    consumers: list[dict[str, object]] = field(default_factory=list)
    syntaxes: set[str] = field(default_factory=set)
    reasons: set[str] = field(
        default_factory=lambda: {
            "dynamic-and-nonliteral-consumers-not-exhaustively-observed"
        }
    )
    consumed: int = 0
    truncated: bool = False
    source_complete: bool = True

    def bound(self, reason: str) -> None:
        self.truncated = True
        self.reasons.add(reason)

    def add(
        self,
        rows: list[dict[str, object]],
        member: dict[str, object],
        size: int,
        syntax: str,
    ) -> None:
        self.members.append(member)
        self.consumed += size
        self.syntaxes.add(syntax)
        if (
            member.get("state") != "known-present"
            or syntax == "reader-text-unavailable"
        ):
            self.source_complete = False
            self.reasons.add("asset-reference-source-unqualified")
        limit = VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
        if len(self.consumers) + len(rows) > limit:
            self.bound("asset-reference-result-bound")
        self.consumers.extend(rows[: max(0, limit - len(self.consumers))])

    def scope(self) -> dict[str, object]:
        return {
            "completeness": "incomplete"
            if self.truncated or not self.source_complete
            else "unknown",
            "source_coverage": "complete"
            if self.source_complete and not self.truncated
            else "incomplete",
            "truncated": self.truncated,
            "negative_evidence_admissible": False,
            "discovery": "indexed-basename-token-conjunction",
            "observed_syntax": sorted(self.syntaxes),
            "reasons": sorted(self.reasons),
            "candidate_limit": VERIFICATION_RELEVANCE_DEFAULTS.literal_file_reader_paths,
            "returned_reference_limit": VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites,
            "max_member_bytes": VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes,
            "max_total_bytes": VERIFICATION_RELEVANCE_DEFAULTS.asset_reference_total_bytes,
            "observed_source_bytes": self.consumed,
        }


class VerificationAssetsMixin:
    """Positive bounded references, never a docs-only or no-behavior verdict."""

    def _asset_consumer(
        self, reader: str, target: str, max_bytes: int
    ) -> tuple[list[dict[str, object]], dict[str, object], int, str]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        member, raw = self.source._bounded_source_observation(reader, max_bytes)
        if raw is not None or member.get("reason") == "member-revision-mismatch":
            self.source.ensure_current(reader)
        if raw is None:
            return [], member, 0, str(member.get("reason") or "reader-unavailable")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return [], member, len(raw), "reader-text-unavailable"
        if "\x00" in text:
            return [], member, len(raw), "reader-text-unavailable"
        imported, ambiguous = (
            self.imports._resolve_import_owner_evidence(reader, "pathlib.Path")
            if reader.endswith(".py")
            else ((), False)
        )
        references, syntax = asset_references(
            text,
            reader,
            target,
            python_import_qualified=not imported and not ambiguous,
        )
        rows = [
            {
                **reference,
                "path": reader,
                "domains": [
                    domain.value for domain in classify_repository_path(reader)
                ],
                "source_member": member,
            }
            for reference in references
        ]
        return rows, member, len(raw), syntax

    def _asset_observation(
        self, path: str, source: Mapping[str, object]
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        content = cast("Mapping[str, object]", source["content"])
        if not _asset_candidate(path, content):
            return None
        terms = sorted({row.token for row in lexical_records(PurePosixPath(path).name)})
        limit = VERIFICATION_RELEVANCE_DEFAULTS.literal_file_reader_paths
        member_bytes = VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes
        total_bytes = VERIFICATION_RELEVANCE_DEFAULTS.asset_reference_total_bytes
        candidates = [
            row
            for row in self.reads.lexical_file_candidates(terms, limit=limit + 2)
            if row["matches"] == len(terms) and row["path"] != path
        ]
        state = _AssetConsumers([dict(cast("Mapping[str, object]", source["member"]))])
        if not terms:
            state.source_complete = False
            state.reasons.add("asset-basename-tokenization-unavailable")
        if len(candidates) > limit:
            state.bound("asset-reference-candidate-bound")
        for candidate in candidates[:limit]:
            reader = str(candidate["path"])
            if state.consumed >= total_bytes:
                state.bound("asset-reference-byte-bound")
                break
            state.add(
                *self._asset_consumer(
                    reader, path, min(member_bytes, total_bytes - state.consumed)
                )
            )
        packet: dict[str, object] = {
            "schema": "hashmarks.repository-asset.v1",
            "content": dict(content),
            "path_domains": [domain.value for domain in classify_repository_path(path)],
            "consumers": state.consumers,
            "supporting_source_members": state.members,
            "consumer_scope": state.scope(),
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        packet["evidence_identity"] = evidence_identity(
            "hashmarks.repository-asset.v1", packet
        )
        return packet
