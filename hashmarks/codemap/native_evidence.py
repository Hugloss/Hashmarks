"""Native producer publication and source-bound evidence qualification."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hashmarks import native_vitest
from hashmarks.native_vitest import VitestViteGraph

from .evidence_freshness import EvidenceFreshnessMixin
from .project_graph import ProjectGraphProvider, default_project_graph_providers
from .pyright_type_server import PyrightTypeServerProvider
from .scip_adapter import load_scip_json
from .scip_import import (
    collect_scip_rows,
    publish_scip_claim_metadata,
    scip_reference_rows,
)
from .scip_relationship_adapter import scip_import_provenance
from .typescript_resolver import TypeScriptResolverProvider

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .project_graph import ProjectEdge, ProjectNode
    from .repository_file_discovery import RepositoryFiles
    from .repository_index_store import WorkspaceMapStore
    from .repository_source import RepositorySource


@dataclass
class NativeEvidenceProducers:
    """The explicit native producers consumed at this translation boundary."""

    projects: tuple[ProjectGraphProvider, ...]
    typescript: TypeScriptResolverProvider = field(
        default_factory=TypeScriptResolverProvider
    )
    pyright: PyrightTypeServerProvider = field(
        default_factory=PyrightTypeServerProvider
    )
    vitest_detect: Callable[[Path], Path | None] = field(
        default_factory=lambda: native_vitest.local_vitest
    )
    vitest_collect: Callable[[Path], VitestViteGraph] = field(
        default_factory=lambda: native_vitest.collect_vitest_vite_graph
    )


class RepositoryNativeEvidence(EvidenceFreshnessMixin):
    """Own admitted producer rows and their atomic freshness/provenance binding."""

    def __init__(
        self,
        files: RepositoryFiles,
        source: RepositorySource,
        reads: DecisionScope,
        store: WorkspaceMapStore,
        producers: NativeEvidenceProducers | None = None,
    ) -> None:
        self.files = files
        self.source = source
        self.reads = reads
        self.store = store
        self.workspace = files.workspace
        self.producers = (
            NativeEvidenceProducers(
                default_project_graph_providers(files.visible_manifests)
            )
            if producers is None
            else producers
        )

    def import_scip(
        self, path: str | Path, *, provenance: Mapping[str, Any] | None = None
    ) -> dict[str, object]:
        """Import admitted native records and their direct producer claims atomically."""
        self.reads.ready()
        raw_path = Path(path)
        if not raw_path.is_absolute():
            raw_path = self.workspace / raw_path
        producer, occurrences, warnings = load_scip_json(
            raw_path, workspace=self.workspace
        )
        qualified_provenance = scip_import_provenance(
            provenance, sorted({row.path for row in occurrences})
        )
        rows = collect_scip_rows(self, producer, occurrences, qualified_provenance)
        with self.store.publication_transaction():
            previous_generation = self.store.generation()
            generation = self.store.bump_generation()
            self._carry_forward_evidence_generation(
                previous_generation=previous_generation, generation=generation
            )
            self.store.replace_native_occurrences(
                producer, rows.definitions, scip_reference_rows(rows.references)
            )
            self._record_evidence_snapshot(
                "scip", producer, bind_generation=True, generation=generation
            )
            publish_scip_claim_metadata(self, producer, rows, qualified_provenance)
            self.store.set_meta("scip_last_import_unix", str(time.time()))
        return {
            "schema": "hashmarks.scip-import.v1",
            "producer": producer,
            "definitions": len(rows.definitions),
            "references": len(rows.references),
            "skipped": rows.skipped,
            "warnings": list(warnings),
            "unlocated_relationship_claims": len(rows.unlocated),
            "unlocated_relationship_omitted": rows.unlocated_omitted,
        }

    @staticmethod
    def _project_node_value(node: object, name: str) -> object:
        if isinstance(node, dict):
            return node.get(name)
        return getattr(node, name, None)

    def _project_node_admitted(self, node: object) -> bool:
        manifest = str(self._project_node_value(node, "manifest") or "")
        metadata_raw = self._project_node_value(node, "metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        freshness = metadata.get("freshness_manifests") or ()
        manifests = (manifest, *(str(value) for value in freshness))
        if any(self.files.visible_file(value) is None for value in manifests):
            return False
        root = str(self._project_node_value(node, "root") or "").strip("/")
        if root in {"", "."}:
            return True
        return self.files.has_visible_file(root)

    def _admitted_external_project_ids(self, producer: str) -> set[str]:
        return {
            str(row.get("project_id") or "")
            for row in self._fresh_project_nodes()
            if str(row.get("producer") or "") != producer
            and self._project_node_admitted(row)
        }

    def _admit_project_graph(
        self,
        provider_name: str,
        nodes: tuple[ProjectNode, ...],
        edges: tuple[ProjectEdge, ...],
    ) -> tuple[tuple[ProjectNode, ...], tuple[ProjectEdge, ...], int, int]:
        admitted_nodes = tuple(
            node for node in nodes if self._project_node_admitted(node)
        )
        admitted_ids = {
            str(self._project_node_value(node, "project_id") or "")
            for node in admitted_nodes
        }
        known_ids = admitted_ids | self._admitted_external_project_ids(provider_name)
        admitted_edges = tuple(
            edge
            for edge in edges
            if str(self._project_node_value(edge, "source") or "") in known_ids
            and str(self._project_node_value(edge, "target") or "") in known_ids
        )
        return (
            admitted_nodes,
            admitted_edges,
            len(nodes) - len(admitted_nodes),
            len(edges) - len(admitted_edges),
        )

    def _enrich_project_graphs(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
        ensure_publication_generation: Callable[[], int],
    ) -> None:
        for provider in self.producers.projects:
            if selected is not None and provider.name not in selected:
                continue
            if not provider.detect(self.workspace):
                continue
            evidence = provider.collect(self.workspace)
            nodes, edges, filtered_nodes, filtered_edges = self._admit_project_graph(
                provider.name,
                evidence.nodes,
                evidence.edges,
            )
            if (
                provider.topology_manifest is not None
                and self.files.visible_file(provider.topology_manifest) is None
            ):
                nodes = ()
                edges = ()
                filtered_nodes = len(evidence.nodes)
                filtered_edges = len(evidence.edges)
            generation = ensure_publication_generation()
            self.store.replace_project_graph(provider.name, nodes, edges)
            project_manifests = [
                manifest
                for node in nodes
                for manifest in (
                    node.manifest,
                    *(node.metadata.get("freshness_manifests") or ()),
                )
            ]
            # A provider topology manifest can own edge-only graph evidence even
            # when the provider contributes no project nodes.
            if provider.topology_manifest is not None:
                project_manifests.insert(0, provider.topology_manifest)
            self._record_evidence_snapshot(
                "project",
                provider.name,
                bind_generation=provider.bind_generation,
                manifests=project_manifests,
                generation=generation,
            )
            results.append(
                {
                    "producer": evidence.producer,
                    "projects": len(nodes),
                    "edges": len(edges),
                }
            )
            warnings.extend(evidence.warnings)
            if filtered_nodes or filtered_edges:
                warnings.append(
                    f"{provider.name}: filtered project evidence outside repository admission "
                    f"(projects={filtered_nodes}, edges={filtered_edges})"
                )

    def _enrich_typescript_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
        ensure_publication_generation: Callable[[], int],
    ) -> None:
        if selected is None or self.producers.typescript.name in selected:
            if self.producers.typescript.detect(self.workspace):
                ts = self.producers.typescript.collect(self.workspace)
                generation = ensure_publication_generation()
                self.store.replace_native_file_edges(
                    self.producers.typescript.name, ts.edges
                )
                self._record_evidence_snapshot(
                    "native-file",
                    ts.producer,
                    bind_generation=True,
                    manifests=("tsconfig.json",),
                    generation=generation,
                )
                results.append({"producer": ts.producer, "file_edges": len(ts.edges)})
                warnings.extend(ts.warnings)

    def _enrich_pyright_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
        ensure_publication_generation: Callable[[], int],
    ) -> None:
        if selected is None or self.producers.pyright.name in selected:
            if self.producers.pyright.detect(self.workspace):
                python_sources = [
                    str(row["path"])
                    for row in self.store.all_file_rows()
                    if str(row.get("language") or "") == "python"
                ]
                pyright = self.producers.pyright.collect(self.workspace, python_sources)
                generation = ensure_publication_generation()
                self.store.replace_native_file_edges(
                    self.producers.pyright.name, pyright.edges
                )
                self._record_evidence_snapshot(
                    "native-file",
                    pyright.producer,
                    bind_generation=True,
                    manifests=("pyrightconfig.json", "pyproject.toml"),
                    generation=generation,
                )
                results.append(
                    {
                        "producer": pyright.producer,
                        "file_edges": len(pyright.edges),
                        "protocol_version": pyright.protocol_version,
                    }
                )
                warnings.extend(pyright.warnings)

    def _enrich_vitest_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
        ensure_publication_generation: Callable[[], int],
    ) -> None:
        if selected is None or "vitest-vite" in selected:
            if self.producers.vitest_detect(self.workspace) is not None:
                vite = self.producers.vitest_collect(self.workspace)
                if vite.command or vite.edges:
                    generation = ensure_publication_generation()
                    self.store.replace_native_file_edges(vite.producer, vite.edges)
                    self._record_evidence_snapshot(
                        "native-file",
                        vite.producer,
                        bind_generation=True,
                        manifests=(
                            "package.json",
                            "vitest.config.ts",
                            "vitest.config.js",
                            "vitest.config.mts",
                            "vitest.config.mjs",
                            "vite.config.ts",
                            "vite.config.js",
                            "vite.config.mts",
                            "vite.config.mjs",
                        ),
                        generation=generation,
                    )
                    results.append(
                        {"producer": vite.producer, "file_edges": len(vite.edges)}
                    )
                warnings.extend(vite.warnings)

    def enrich_projects(
        self,
        providers: Iterable[str] | None = None,
        *,
        expected_generation: int | None = None,
    ) -> dict[str, object]:
        """Collect slower/native package graph evidence explicitly in the enrichment lane."""
        selected = None if providers is None else {str(value) for value in providers}
        results: list[dict[str, object]] = []
        warnings: list[str] = []
        publication_generation: int | None = None

        def ensure_publication_generation() -> int:
            nonlocal publication_generation
            if publication_generation is None:
                previous_generation = self.store.generation()
                publication_generation = self.store.bump_generation()
                self._carry_forward_evidence_generation(
                    previous_generation=previous_generation,
                    generation=publication_generation,
                )
            return publication_generation

        with self.store.publication_transaction():
            current_generation = self.store.generation()
            if (
                expected_generation is not None
                and current_generation != expected_generation
            ):
                raise RuntimeError(
                    "CodeMap generation changed before project enrichment "
                    f"({expected_generation} -> {current_generation})"
                )
            self._enrich_project_graphs(
                selected, results, warnings, ensure_publication_generation
            )
            self._enrich_typescript_graph(
                selected, results, warnings, ensure_publication_generation
            )
            self._enrich_pyright_graph(
                selected, results, warnings, ensure_publication_generation
            )
            self._enrich_vitest_graph(
                selected, results, warnings, ensure_publication_generation
            )
            if publication_generation is not None:
                self.store.set_meta("project_graph_last_sync_unix", str(time.time()))
        return {
            "schema": "hashmarks.codemap-project-enrichment.v1",
            "generation": (
                self.store.generation()
                if publication_generation is None
                else publication_generation
            ),
            "providers": results,
            "projects": self._fresh_project_nodes(),
            "edges": self._fresh_project_edges(),
            "native_file_edges": self._fresh_native_file_edges(),
            "warnings": list(dict.fromkeys(warnings)),
        }
