"""Task-local disclosure of already qualified Python field declarations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility
from .query_primitives import _TASK_STOPWORDS, _query_terms
from .repository_declaration_provider import RepositoryDeclarationProviderError
from .static_python_backend_declarations import StaticPythonBackendDeclarations

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks
    from .task_evidence_types import TaskEvidenceDraft


def _field_groups(discovery: Mapping[str, object]) -> list[dict[str, object]]:
    declarations = cast("Mapping[str, object]", discovery["declarations"])
    groups = cast("list[dict[str, object]]", declarations["groups"])
    rows = []
    for group in groups:
        for declaration in cast("list[dict[str, object]]", group["declarations"]):
            value = cast("Mapping[str, object]", declaration["value"])
            if not value.get("fields"):
                continue
            rows.append(
                {
                    "scope": group["scope"],
                    "coverage": group["coverage"],
                    "correspondence": group["correspondence"],
                    "absence": group["absence"],
                    "value": value,
                    "value_state": declaration["value_state"],
                    "semantic_value_authority": declaration["semantic_value_authority"],
                    "evidence_state": declaration["evidence_state"],
                    "producer": declaration["producer"],
                }
            )
    return sorted(
        rows,
        key=lambda row: cast("Mapping[str, int]", row["scope"])["class_line"],
    )


def _initial_field_selection(
    groups: list[dict[str, object]], task: str
) -> dict[str, object]:
    terms = set(_query_terms(task)) - _TASK_STOPWORDS
    fields = [
        (group_index, field_index, field)
        for group_index, group in enumerate(groups)
        for field_index, field in enumerate(
            cast(
                "list[dict[str, object]]",
                cast("Mapping[str, object]", group["value"])["fields"],
            )
        )
    ]
    matches = [
        [group, index]
        for group, index, field in fields
        if terms.intersection(_query_terms(str(field["name"])))
    ]
    selected = matches if matches else [[group, index] for group, index, _ in fields]
    return {
        "basis": "field-name-terms-else-source-order",
        "selection_authority": False,
        "bound": 3,
        "matched": len(matches),
        "fields": selected[:3],
    }


class TaskEvidenceFieldsMixin:
    def _task_evidence_field_declarations(
        self, path: str, task: str
    ) -> dict[str, object] | None:
        """Reuse the declaration owner; do not parse or interpret field syntax."""
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        qualification: dict[str, object] = {
            "scope": "explicit-python-file-declared-fields",
            "ownership_authority": False,
            "negative_evidence_admissible": False,
            "coverage": "incomplete",
            "bound": 3,
        }
        provider = StaticPythonBackendDeclarations(
            paths=(path,),
            include_model_fields=False,
            include_environment_reads=False,
            include_class_fields=True,
        )
        try:
            discovery = self.declarations.discover([provider])
        except RepositoryDeclarationProviderError:
            # Optional disclosure cannot turn a provider failure into absence.
            # No partial groups or exception text enter the task packet.
            return {
                **qualification,
                "state": "unavailable",
                "reason": "declaration-provider-failed",
            }
        providers = cast("list[dict[str, object]]", discovery["providers"])
        inputs = cast("list[dict[str, object]]", providers[0]["inputs"])
        groups = _field_groups(discovery)
        if not groups:
            return None
        return {
            **qualification,
            "state": "observed",
            "repository": discovery["repository"],
            "source_revision": inputs[0]["member_revision"],
            "provider": providers[0]["provenance"],
            "discovery_identity": discovery["observation_identity"],
            "observed": len(groups),
            "returned": min(len(groups), 3),
            "omitted": max(0, len(groups) - 3),
            "groups": groups[:3],
            "initial_field_selection": _initial_field_selection(groups[:3], task),
        }

    def _task_evidence_attach_field_declarations(
        self, packet: TaskEvidenceDraft
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        target = packet["explicit_target"]
        path = target["path"]
        if target["basis"] != "literal-path" or not path or not path.endswith(".py"):
            return
        if (
            not self.index.is_current(path)
            or self._task_evidence_visibility(path) is not EvidenceVisibility.SOURCE
            or self.files.decide(path).evidence_visibility
            is not EvidenceVisibility.SOURCE
        ):
            return
        row = next(
            (row for row in packet["retrieval"]["results"] if row["path"] == path),
            None,
        )
        if row is not None:
            context = self._task_evidence_field_declarations(path, packet["task"])
            if context is not None and self.index.is_current(path):
                row["field_declarations"] = context
