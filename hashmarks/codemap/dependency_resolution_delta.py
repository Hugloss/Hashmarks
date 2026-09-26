from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin


class DependencyResolutionDeltaMixin:
    """Compare qualified dependency observations within one repository authority."""

    def dependency_resolution_delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        for observation in (before, after):
            DependencyResolutionEvidenceMixin._require_qualified_dependency_observation_v3(
                observation
            )
        before_binding = cast("Mapping[str, object]", before["repository_binding"])
        after_binding = cast("Mapping[str, object]", after["repository_binding"])
        if (
            before_binding.get("repository_identity")
            != after_binding.get("repository_identity")
            or before_binding.get("repository_identity")
            != self._repository_packet_identity()
        ):
            raise ValueError("dependency observations repository-mismatch")
        return DependencyResolutionEvidenceMixin._dependency_resolution_delta_v3(
            before, after
        )
