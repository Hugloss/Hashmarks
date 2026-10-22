"""Source observation for supplied flat membership; never native collection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)

from .decision_session import decision_scoped, reconcile_decision
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


    @staticmethod
    def _nomination_member_correspondence(
        claimed: dict[str, object], observed: dict[str, object]
    ) -> str:
        """Compare claims with the sole native source observer's already-read fact."""
        state = observed.get("state")
        if state not in {"known-present", "known-absent"}:
            return "unknown"
        if state != claimed["state"]:
            return "mismatch"
        if state == "known-present" and (
            observed.get("member_revision") != claimed.get("member_revision")
        ):
            return "mismatch"
        return "matched"

    def _observe_nomination_source_member(self, path: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        self.source.ensure_current(path)
        return self._collection_source_member(path)

    @operation_response("verification_nomination_binding")
    @reconcile_decision
    @decision_scoped
    def observe_nomination_source_binding(
        self, nomination: object
    ) -> dict[str, object]:
        """Correlate an existing nomination with current observed input revisions.

        Only structural validation and native member observation establish
        facts here. A match is not producer authentication, a freshness lease,
        verifier selection, or permission to execute tests.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        structurally = validate_verification_nomination(nomination)
        state = "invalid-packet"
        reasons = list(structurally["reasons"])
        checks: list[dict[str, object]] = []
        if structurally["valid"]:
            assert isinstance(nomination, dict)
            state = "not-applicable"
            if nomination["available"] is True:
                assert isinstance(nomination["supporting_source_members"], list)
                observed_by_path: list[dict[str, object]] = []
                for claimed in nomination["supporting_source_members"]:
                    assert isinstance(claimed, dict)
                    path = str(claimed["path"])
                    observed = self._observe_nomination_source_member(path)
                    observed_by_path.append(observed)
                    relation = self._nomination_member_correspondence(
                        claimed, observed
                    )
                    checks.append(
                        {"path": path, "correspondence": relation}
                    )
                    if relation != "matched":
                        reasons.append(f"source-{relation}:{path}")
                # A single read scope does not prevent source files changing on
                # disk. Reobserve each participant before reporting matched.
                for row, originally in zip(checks, observed_by_path, strict=True):
                    current = self._observe_nomination_source_member(str(row["path"]))
                    if current != originally:
                        row["correspondence"] = "unknown"
                        reasons.append(
                            f"source-changed-during-observation:{row['path']}"
                        )
                relations = {row["correspondence"] for row in checks}
                state = (
                    "mismatch"
                    if "mismatch" in relations
                    else "unknown"
                    if "unknown" in relations
                    else "matched"
                )
        return {
            "schema": operation_schema("verification_nomination_binding"),
            "nomination_identity": structurally["nomination_identity"],
            "packet_valid": structurally["valid"],
            "source_binding_state": state,
            "checked_source_members": checks,
            "reasons": list(dict.fromkeys(reasons)),
            "authority": "current-source-correspondence-only",
            "producer_authenticity": "not-checked",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
        }
