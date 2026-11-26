"""Task-local disclosure of already qualified Python field declarations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility, symbol_occurrence_parts
from .query_primitives import _TASK_STOPWORDS, _WORD_RE, _query_terms
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


def _qualified_field_query(task: str) -> tuple[set[str], str]:
    """Separate whole dotted Python spellings from independently requested words."""
    words = "".join(
        ch if ch == "." or ("_" + ch).isidentifier() else " " for ch in task
    ).split()
    dotted: set[str] = set()
    bare: list[str] = []
    for word in words:
        # A trailing period may end a sentence. A leading dot can instead
        # continue a computed receiver, as in items[0].Client.timeout.
        word = word.rstrip(".")
        if "." in word and all(part.isidentifier() for part in word.split(".")):
            dotted.add(unicodedata.normalize("NFKC", word))
        else:
            bare.append(word)
    return dotted, " ".join(bare)


def _lexical_field_matches(
    fields: list[tuple[int, int, str]], task: str
) -> list[tuple[int, int]]:
    terms = set(_query_terms(task)) - _TASK_STOPWORDS
    literal_names = set(_WORD_RE.findall(task)) - _TASK_STOPWORDS
    exact: list[tuple[int, int]] = []
    partial: list[tuple[int, int]] = []
    for group, index, name in fields:
        if name in literal_names:
            exact.append((group, index))
        elif terms.intersection(_query_terms(name)):
            partial.append((group, index))
    return exact + partial


def _field_positions(groups: list[dict[str, object]]) -> list[tuple[int, int, str]]:
    return [
        (group_index, field_index, str(field["name"]))
        for group_index, group in enumerate(groups)
        for field_index, field in enumerate(
            cast(
                "list[dict[str, object]]",
                cast("Mapping[str, object]", group["value"])["fields"],
            )
        )
    ]


def _qualified_field_matches(
    groups: list[dict[str, object]],
    fields: list[tuple[int, int, str]],
    symbols: Sequence[Mapping[str, object]],
    dotted: set[str],
) -> list[tuple[int, int]]:
    classes = {
        (row["name"], row["start_line"]): symbol_occurrence_parts(str(row["qualname"]))[
            0
        ]
        for row in symbols
        if row["kind"] == "class"
    }
    scopes = [cast("Mapping[str, object]", group["scope"]) for group in groups]
    owners = [
        classes.get((scope["class_name_syntax"], scope["class_line"]))
        for scope in scopes
    ]
    return [
        (group, index)
        for group, index, name in fields
        if owners[group] is not None and f"{owners[group]}.{name}" in dotted
    ]


def _select_field_groups(
    groups: list[dict[str, object]],
    fields: list[tuple[int, int, str]],
    task: str,
    qualified: list[tuple[int, int]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Match declarations before applying the group and field display limits."""
    matches = list(dict.fromkeys([*qualified, *_lexical_field_matches(fields, task)]))
    ordered_groups = dict.fromkeys(group for group, _ in matches)
    if not qualified:
        ordered_groups.update(dict.fromkeys(range(len(groups))))
    group_indexes = sorted(list(ordered_groups)[:3])
    retained = [groups[i] for i in group_indexes]
    projected_group = {original: index for index, original in enumerate(group_indexes)}
    selected = matches or [(group, index) for group, index, _ in fields]
    return retained, {
        "basis": "qualified-class-field-then-literal-field-name-and-terms"
        if qualified
        else "literal-field-name-then-terms-else-source-order",
        "selection_authority": False,
        "bound": 3,
        "matched": len(matches),
        "fields": [
            [projected_group[group], index] for group, index in sorted(selected[:3])
        ],
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
        retained, selection = self._task_evidence_select_fields(
            path, task, groups, inputs[0]["member_revision"]
        )
        return {
            **qualification,
            "state": "observed",
            "repository": discovery["repository"],
            "source_revision": inputs[0]["member_revision"],
            "provider": providers[0]["provenance"],
            "discovery_identity": discovery["observation_identity"],
            "observed": len(groups),
            "returned": len(retained),
            "omitted": len(groups) - len(retained),
            "groups": retained,
            "initial_field_selection": selection,
        }

    def _task_evidence_select_fields(
        self, path: str, task: str, groups: list[dict[str, object]], revision: object
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        """Use an indexed class spelling only for the same revision as the declaration."""
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        query = re.sub(
            rf"(?<![\w.]){re.escape(path)}(?!\w|\.\w)",
            " ",
            self._task_evidence_retrieval_query(task),
        )
        fields = _field_positions(groups)
        qualified = []
        dotted, bare = _qualified_field_query(query) if "." in query else (set(), query)
        if dotted:
            member = self.reads.file_row(path)
            if member is not None and member["file_digest"] == revision:
                if module := member["module_name"]:
                    prefix = f"{module}."
                    dotted |= {
                        name.removeprefix(prefix)
                        for name in dotted
                        if name.startswith(prefix)
                    }
                qualified = _qualified_field_matches(
                    groups, fields, self.reads.symbols_for_path(path), dotted
                )
        return _select_field_groups(
            groups, fields, bare if qualified else query, qualified
        )

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
