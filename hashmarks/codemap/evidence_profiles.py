from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, cast

from .change_impact import ChangeImpactOptions
from .decision_session import diagnostic_producer

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap

_PROFILE_NAMES = frozenset({"compact", "standard", "audit"})


class EvidenceProfilesMixin:
    """Density projections over one authoritative repository-intelligence snapshot.

    Profiles never persist or independently own repository facts.  Each projection
    names the exact F3 snapshot it came from so consumers can trade context size
    for evidence detail without creating another source of truth.
    """

    @staticmethod
    def _profile_mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def _compact_profile_evidence(
        cls, snapshot: Mapping[str, object]
    ) -> dict[str, object]:
        repository = cls._profile_mapping(snapshot.get("repository"))
        path_rows = cls._profile_mapping(snapshot.get("paths"))
        paths = {
            str(path): {"revision": cls._profile_mapping(row).get("revision")}
            for path, row in path_rows.items()
        }

        affected: dict[str, list[dict[str, object]]] = {}
        for role, raw_rows in cls._profile_mapping(snapshot.get("affected")).items():
            if not isinstance(raw_rows, list):
                continue
            rows: list[dict[str, object]] = []
            for raw in raw_rows:
                if not isinstance(raw, Mapping) or not raw.get("path"):
                    continue
                row: dict[str, object] = {"path": str(raw["path"])}
                if "selected" in raw:
                    row["selected"] = bool(raw["selected"])
                rows.append(row)
            if rows:
                affected[str(role)] = rows

        verification = cls._profile_mapping(snapshot.get("verification"))
        freshness = {
            str(key): {
                field: deepcopy(row[field])
                for field in ("state", "evidence_identity")
                if field in row
            }
            for key, raw in cls._profile_mapping(snapshot.get("freshness")).items()
            if (row := cls._profile_mapping(raw))
        }
        payload: dict[str, object] = {
            "repository": {
                key: repository[key]
                for key in ("repository_identity", "source_identity")
                if key in repository
            },
            "task_identity": snapshot.get("task_identity"),
            "paths": paths,
            "affected": affected,
            "verification": {
                key: deepcopy(verification[key])
                for key in ("member", "reason")
                if key in verification
            },
            "freshness": freshness,
        }
        if snapshot.get("project_impact") is not None:
            project = cls._profile_mapping(snapshot.get("project_impact"))
            payload["provenance"] = {
                key: deepcopy(project[key])
                for key in (
                    "schema",
                    "identity",
                    "project_identity",
                    "producer_identity",
                )
                if key in project
            }
        return payload

    @classmethod
    def _standard_profile_evidence(
        cls, snapshot: Mapping[str, object]
    ) -> dict[str, object]:
        verification = cls._profile_mapping(snapshot.get("verification"))
        payload: dict[str, object] = {
            "repository": deepcopy(snapshot.get("repository")),
            "task_identity": snapshot.get("task_identity"),
            "paths": deepcopy(snapshot.get("paths") or {}),
            "affected": deepcopy(snapshot.get("affected") or {}),
            "ownership": deepcopy(snapshot.get("ownership")),
            "verification": {
                key: deepcopy(verification[key])
                for key in ("member", "test_symbol", "reason")
                if key in verification
            },
            "freshness": deepcopy(snapshot.get("freshness") or {}),
            "bounds": deepcopy(snapshot.get("bounds") or {}),
        }
        if snapshot.get("project_impact") is not None:
            payload["project_impact"] = deepcopy(snapshot["project_impact"])
        return payload

    @staticmethod
    def _audit_profile_evidence(snapshot: Mapping[str, object]) -> dict[str, object]:
        return {"snapshot": deepcopy(dict(snapshot))}

    def _profile_from_snapshot(
        self,
        snapshot: Mapping[str, object],
        *,
        profile: str,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        profile_name = str(profile).strip().lower()
        if profile_name not in _PROFILE_NAMES:
            raise ValueError("profile must be one of: audit, compact, standard")
        if snapshot.get("schema") != "hashmarks.repository-intelligence-snapshot.v1":
            raise ValueError(
                "snapshot must be hashmarks.repository-intelligence-snapshot.v1"
            )
        snapshot_identity = str(snapshot.get("snapshot_identity") or "")
        if not snapshot_identity:
            raise ValueError("snapshot is missing snapshot_identity")

        if profile_name == "compact":
            evidence = self._compact_profile_evidence(snapshot)
        elif profile_name == "standard":
            evidence = self._standard_profile_evidence(snapshot)
        else:
            evidence = self._audit_profile_evidence(snapshot)

        payload: dict[str, object] = {
            "schema": "hashmarks.evidence-profile.v1",
            "profile": profile_name,
            "source_snapshot_identity": snapshot_identity,
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
            "evidence": evidence,
        }
        payload["profile_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.evidence-profile.v1",
            payload,
        )
        return payload

    @diagnostic_producer
    def repository_intelligence_profile(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        profile: str = "compact",
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions = ChangeImpactOptions(
            impact_limit_per_surface=4,
            max_depth=3,
        ),
    ) -> dict[str, object]:
        """Project one bounded F3 snapshot at compact, standard, or audit density."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        snapshot = self.repository_intelligence_snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
        )
        return self._profile_from_snapshot(snapshot, profile=profile)
