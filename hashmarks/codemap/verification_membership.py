"""Source observation for supplied flat membership; never native collection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import operation_response
from hashmarks.verification_collection import (
    collection_bundle,
    collection_inputs,
    normalize_collection_report,
)
from hashmarks.verification_collection_observation import membership_observation

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification


class VerificationMembershipMixin:
    def _collection_source_member(self, path: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        observation = self.source.observe(path)
        member = observation["member"]
        assert isinstance(member, dict)
        return dict(member)

    @operation_response("verification_membership")
    def observe_membership(self, report: object) -> dict[str, object]:
        """Bind an explicit supplied selection/collection report to current source.

        Revision claims must describe the producer's observed inputs. Missing
        claims remain unknown: current source bytes cannot retrospectively prove
        which bytes an external collector used.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        normalized = normalize_collection_report(report)
        with self.reads.session():
            source_members = [
                self._collection_source_member(str(row["path"]))
                for row in collection_inputs(normalized)
            ]
            correlation = self._collection_correlation.observe(
                [collection_bundle(normalized)], include_relationships=False
            )
            result = membership_observation(normalized, correlation, source_members)
            for observed in source_members:
                path = str(observed["path"])
                current = self._collection_source_member(path)
                if current != observed:
                    raise UnstableFileError(
                        f"verification membership source changed during observation: {path}"
                    )
            return result
