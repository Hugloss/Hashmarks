from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence

_SCHEMA = "hashmarks.dependency-resolution.v3"
_LIST_LINE = re.compile(
    r"^[ \t]*(?P<coordinate>[^ \t:]+:[^ \t:]+:[^ \t:]+"
    r"(?::[^ \t:]+){2,3})(?:[ \t]+--[ \t]+module[ \t]+"
    r"(?P<module>.+?))?[ \t]*$"
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_INCOMPLETE_RESOLUTION_WARNINGS = (
    "no dependency information available",
    "could not be resolved",
    "failed to read artifact descriptor",
)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _coordinate(
    group: str,
    artifact: str,
    packaging: str,
    classifier: str,
    version: str,
) -> tuple[str, str]:
    component = f"{group}:{artifact}"
    variant = f":{classifier}" if classifier else ""
    return component, f"{component}:{packaging}{variant}:{version}"


def _tree_node(raw: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    group = str(raw.get("groupId") or "").strip()
    artifact = str(raw.get("artifactId") or "").strip()
    packaging = str(raw.get("type") or "jar").strip()
    classifier = str(raw.get("classifier") or "").strip()
    version = str(raw.get("version") or "").strip()
    scope = str(raw.get("scope") or "").strip()
    if not group or not artifact or not version:
        raise ValueError("Maven tree node requires groupId, artifactId, and version")
    component, node = _coordinate(group, artifact, packaging, classifier, version)
    return component, node, group, artifact, version, scope


def _list_coordinate(text: str) -> tuple[str, str, str, str, str, str]:
    parts = text.split(":")
    if len(parts) == 5:
        group, artifact, packaging, version, scope = parts
        classifier = ""
    elif len(parts) == 6:
        group, artifact, packaging, classifier, version, scope = parts
    else:
        raise ValueError(f"unsupported Maven dependency-list coordinate: {text}")
    component, node = _coordinate(group, artifact, packaging, classifier, version)
    return component, node, group, artifact, version, scope


def _module_name(text: str) -> str:
    value = text.strip()
    for suffix in (" [auto]", " (auto)"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].rstrip()
    if not value:
        raise ValueError("Maven dependency-list module must not be empty")
    return value


# This is the cohesive translation boundary between Maven's two artifact shapes and
# the dependency-resolution v3 contract. Splitting its state across wrapper helpers
# would obscure the inventory/graph/ownership invariants it must preserve.
def maven_dependency_observation(  # noqa: C901, PLR0912, PLR0914, PLR0915
    *,
    trees: Mapping[str, bytes],
    inventories: Mapping[str, bytes],
    complete_tree_contexts: Sequence[str] = (),
    complete_inventory_contexts: Sequence[str] = (),
    repository_inputs: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Translate already-produced Maven tree/list evidence into the v3 contract.

    This adapter is deliberately execution-free: callers provide Maven output bytes.
    Hashmarks does not invoke Maven, resolve packages, or inspect dependency source.
    """
    contexts = sorted(set(trees) | set(inventories))
    if not contexts:
        raise ValueError("at least one Maven dependency context is required")
    complete_trees = {str(context) for context in complete_tree_contexts}
    complete_inventories = {str(context) for context in complete_inventory_contexts}
    unknown_complete_trees = sorted(complete_trees - set(trees))
    if unknown_complete_trees:
        raise ValueError(
            "complete Maven tree context has no supplied tree: "
            f"{unknown_complete_trees[0]}"
        )
    unknown_complete_inventories = sorted(complete_inventories - set(inventories))
    if unknown_complete_inventories:
        raise ValueError(
            "complete Maven inventory context has no supplied list: "
            f"{unknown_complete_inventories[0]}"
        )

    components: dict[str, dict[str, object]] = {}
    selections: dict[str, dict[str, object]] = {}
    roots: list[dict[str, str]] = []
    relationships: list[dict[str, object]] = []
    inventory: list[dict[str, object]] = []
    ownership: dict[tuple[str, str], set[str]] = defaultdict(set)
    ownership_completeness: dict[str, str] = {}
    evidence_sources: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []

    def admit_selection(
        component_id: str,
        node_id: str,
        artifact: str,
        version: str,
        context: str,
        source_id: str,
    ) -> None:
        components.setdefault(
            component_id,
            {"component_id": component_id, "name": artifact, "ecosystem": "maven"},
        )
        row = selections.setdefault(
            node_id,
            {
                "node_id": node_id,
                "component_id": component_id,
                "version": version,
                "source": "maven",
                "marker": "",
                "contexts": set(),
                "evidence_sources": set(),
            },
        )
        if row["component_id"] != component_id or row["version"] != version:
            raise ValueError(f"conflicting Maven selection identity: {node_id}")
        row["contexts"].add(context)
        row["evidence_sources"].add(source_id)

    for context in contexts:
        selection_sources: list[str] = []
        tree_source = f"tree:{context}"
        if context in trees:
            raw_bytes = trees[context]
            try:
                root_raw = json.loads(raw_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid Maven dependency tree JSON for {context}"
                ) from exc
            if not isinstance(root_raw, Mapping):
                raise ValueError(
                    f"Maven dependency tree root must be an object: {context}"
                )
            selection_sources.append(tree_source)
            evidence_sources.append(
                {
                    "source_id": tree_source,
                    "kind": "maven-dependency-tree",
                    "authorities": ["resolution-graph", "selection"],
                    "context": context,
                    "completeness": "complete",
                    "truncation": "complete",
                    "producer_digest": _digest(raw_bytes),
                }
            )
            coverage.append(
                {
                    "context": context,
                    "kind": "resolution-graph",
                    "completeness": (
                        "complete" if context in complete_trees else "incomplete"
                    ),
                    "truncation": "complete",
                    "evidence_sources": [tree_source],
                }
            )

            def visit(raw: Mapping[str, object], parent: str | None = None) -> str:
                component, node, _group, artifact, version, scope = _tree_node(raw)
                admit_selection(
                    component, node, artifact, version, context, tree_source
                )
                if parent is not None:
                    relationships.append(
                        {
                            "source": parent,
                            "target": node,
                            "kind": "dependency",
                            "context": context,
                            "effective_scope": scope,
                            "marker": "",
                            "evidence_sources": [tree_source],
                        }
                    )
                children = raw.get("children", ())
                if children is None:
                    children = ()
                if not isinstance(children, Sequence) or isinstance(
                    children, (str, bytes, bytearray)
                ):
                    raise ValueError(f"Maven tree children must be a sequence: {node}")
                for child in children:
                    if not isinstance(child, Mapping):
                        raise ValueError(f"Maven tree child must be an object: {node}")
                    visit(child, node)
                return node

            roots.append(
                {
                    "node_id": visit(root_raw),
                    "context": context,
                    "evidence_sources": [tree_source],
                }
            )

        list_source = f"list:{context}"
        if context in inventories:
            raw_bytes = inventories[context]
            try:
                lines = raw_bytes.decode("utf-8").splitlines()
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"invalid Maven dependency list text for {context}"
                ) from exc
            selection_sources.append(list_source)
            evidence_sources.append(
                {
                    "source_id": list_source,
                    "kind": "maven-dependency-list",
                    "authorities": [
                        "module-ownership",
                        "resolved-inventory",
                        "selection",
                    ],
                    "context": context,
                    "completeness": "complete",
                    "truncation": "complete",
                    "producer_digest": _digest(raw_bytes),
                }
            )
            coverage.append(
                {
                    "context": context,
                    "kind": "resolved-inventory",
                    "completeness": (
                        "complete" if context in complete_inventories else "incomplete"
                    ),
                    "truncation": "complete",
                    "evidence_sources": [list_source],
                }
            )
            seen_inventory: set[str] = set()
            module_capable_nodes: set[str] = set()
            module_nodes: set[str] = set()
            header_seen = False
            empty_marker_seen = False
            for raw_line in lines:
                line = _ANSI_ESCAPE.sub("", raw_line)
                if "\x1b" in line:
                    raise ValueError(
                        f"unsupported Maven dependency-list escape: {context}"
                    )
                stripped = line.strip()
                if stripped == "The following files have been resolved:":
                    if header_seen:
                        raise ValueError(
                            f"duplicate Maven dependency-list header for {context}"
                        )
                    header_seen = True
                    continue
                if stripped.startswith("[ERROR]") or stripped == "[INFO] BUILD FAILURE":
                    raise ValueError(f"Maven dependency list contains error: {context}")
                if stripped.startswith("[WARNING]") and any(
                    marker in stripped.lower()
                    for marker in _INCOMPLETE_RESOLUTION_WARNINGS
                ):
                    raise ValueError(
                        "Maven dependency list contains incomplete resolution warning: "
                        f"{context}"
                    )
                if not stripped or stripped.startswith(
                    ("[INFO]", "[WARNING]", "[DEBUG]")
                ):
                    continue
                if not header_seen:
                    raise ValueError(
                        f"Maven dependency-list header is missing: {context}"
                    )
                if stripped == "none":
                    if empty_marker_seen or seen_inventory:
                        raise ValueError(
                            f"conflicting Maven dependency-list empty marker: {context}"
                        )
                    empty_marker_seen = True
                    continue
                match = _LIST_LINE.match(line)
                if match is None:
                    candidate = stripped.split(maxsplit=1)[0]
                    if ":" in candidate:
                        raise ValueError(
                            f"unparsed Maven dependency-list coordinate for {context}: "
                            f"{candidate}"
                        )
                    raise ValueError(
                        f"unrecognized Maven dependency-list content for {context}: "
                        f"{stripped}"
                    )
                if empty_marker_seen:
                    raise ValueError(
                        f"conflicting Maven dependency-list empty marker: {context}"
                    )
                (
                    component,
                    node,
                    _group,
                    artifact,
                    version,
                    _scope,
                ) = _list_coordinate(match.group("coordinate"))
                coordinate_parts = match.group("coordinate").split(":")
                packaging = coordinate_parts[2]
                admit_selection(
                    component, node, artifact, version, context, list_source
                )
                if node not in seen_inventory:
                    if packaging != "pom":
                        module_capable_nodes.add(node)
                    inventory.append(
                        {
                            "node_id": node,
                            "context": context,
                            "evidence_sources": [list_source],
                        }
                    )
                    seen_inventory.add(node)
                module = match.group("module")
                if module is not None:
                    module_nodes.add(node)
                    ownership[(_module_name(module), context)].add(node)
            if not header_seen:
                raise ValueError(f"Maven dependency-list header is missing: {context}")
            module_completeness = (
                "complete"
                if context in complete_inventories
                and module_nodes >= module_capable_nodes
                else "incomplete"
            )
            ownership_completeness[context] = module_completeness
            coverage.append(
                {
                    "context": context,
                    "kind": "module-ownership",
                    "completeness": module_completeness,
                    "truncation": "complete",
                    "evidence_sources": [list_source],
                }
            )

        selection_complete = bool(selection_sources) and (
            (context not in trees or context in complete_trees)
            and (
                context not in inventories
                or context in complete_inventories
            )
        )
        coverage.append(
            {
                "context": context,
                "kind": "selection",
                "completeness": "complete" if selection_complete else "incomplete",
                "truncation": "complete",
                "evidence_sources": sorted(selection_sources),
            }
        )

    normalized_selections = []
    for row in selections.values():
        normalized_selections.append(
            {
                **row,
                "contexts": sorted(row["contexts"]),
                "evidence_sources": sorted(row["evidence_sources"]),
            }
        )

    module_ownership = [
        {
            "module": module,
            "context": context,
            "owners": sorted(owners),
            "completeness": ownership_completeness[context],
            "evidence_sources": [f"list:{context}"],
        }
        for (module, context), owners in ownership.items()
    ]

    return {
        "schema": _SCHEMA,
        "producer": {"kind": "maven-dependency-artifacts", "schema_version": "1"},
        "scope": {},
        "contexts": contexts,
        "roots": sorted(roots, key=lambda row: (row["context"], row["node_id"])),
        "evidence_sources": sorted(evidence_sources, key=lambda row: row["source_id"]),
        "components": sorted(components.values(), key=lambda row: row["component_id"]),
        "selections": sorted(normalized_selections, key=lambda row: row["node_id"]),
        "inventory": sorted(
            inventory, key=lambda row: (row["node_id"], row["context"])
        ),
        "relationships": sorted(
            relationships,
            key=lambda row: (
                row["source"],
                row["target"],
                row["context"],
                row["effective_scope"],
            ),
        ),
        "coverage": sorted(coverage, key=lambda row: (row["context"], row["kind"])),
        "repository_inputs": [dict(row) for row in repository_inputs],
        "module_ownership": sorted(
            module_ownership, key=lambda row: (row["module"], row["context"])
        ),
    }
