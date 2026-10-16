# Diagnostic-to-repository evidence owner census

**Status:** Historical HM-OBS-01 baseline and census snapshot. The subsequent
[implementation and qualification receipt](../qualification/DIAGNOSTIC_CORRESPONDENCE.md)
covers HM-OBS-02..09. **Source inspected:** `e36eb3944b3f4501d60225e8a68574e10b13c986`.
**Scope:** Hashmarks only. No external source, runtime, service or owner approval
is required. The original census stage changed no production code, public API or schema;
the follow-on implementation is recorded separately.

The governing contract is [PRODUCT_BOUNDARY](../reference/PRODUCT_BOUNDARY.md).
Hashmarks owns repository correspondence; producer acquisition, runtime freshness,
interpretation and action stay external. A uniquely resolved current repository
locator can coexist with a mismatched producer source revision. Neither locator
resolution nor a complete repository mapping authenticates producer execution.

## Baseline and reproduction

The working tree was clean before the baseline. The original five-file selection
was recovered from the earlier command, not reconstructed from the number 147.
The earlier historical run emitted no JUnit. A fresh pre-edit rerun produced:

| Test selection | Passed | Failed / errors / skipped |
| --- | ---: | --- |
| `tests/test_diagnostic_delta_validation.py` | 1 | 0 / 0 / 0 |
| `tests/test_diagnostic_member_evidence.py` | 47 | 0 / 0 / 0 |
| `tests/test_evidence_correlation.py` | 79 | 0 / 0 / 0 |
| `tests/test_repository_intelligence_validation.py` | 7 | 0 / 0 / 0 |
| `tests/test_product_boundary.py` | 13 | 0 / 0 / 0 |
| **Total** | **147** | **0 / 0 / 0** |

Environment: Python 3.11.15; interpreter `.venv/bin/python`; platform
`Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`. Duration: 9.27 s.
This is source-test evidence on WSL2, not native runtime qualification.

```bash
XDG_CACHE_HOME=/tmp/hashmarks-plan-cache \
UV_CACHE_DIR=/tmp/hashmarks-plan-uv \
uv run --frozen --offline --no-sync --group test \
python -m pytest -q -p no:cacheprovider --tb=short \
  --junitxml=dist/hm-obs/baseline.xml \
  tests/test_diagnostic_delta_validation.py \
  tests/test_diagnostic_member_evidence.py \
  tests/test_evidence_correlation.py \
  tests/test_repository_intelligence_validation.py \
  tests/test_product_boundary.py
```

Generated review artifacts live under ignored `dist/hm-obs/`. Preserve them with
the handoff rather than treating this historical result as a future measurement:

- `baseline.xml`: original-selection rerun, SHA-256
  `4eed1ce8f9e5cf3d62b07db75459fa0a22a96b52b1b322f203ea9b11fc6d5ad5`.
- `baseline.json`: exact command, commit, clean-tree status, interpreter/platform,
  all 147 collected test identifiers, test-file hashes, configuration hashes and
  JUnit hash. The committed lock was consumed without modification.
- `census-references.json`: pre-edit AST definition/call-spelling evidence for
  selected symbols in tracked `hashmarks/`, `tests/` and `scripts/` Python files.
  File parsing used `hashmarks.python_ast_cache.read_python_ast`. Attribute-call
  spellings are candidates, not proof of Python runtime dispatch.
- `correspondence.xml`: the new two-test module plus existing source-revision and
  source-line suites: **53 passed, 0 failures/errors/skips**, 3.75 s.

The commands require the locked test environment materialized by `make init`.
On a read-only home, set the two cache variables for setup and subsequent checks.
Neither cache placement nor unavailable optional host tools changes source truth.

## Census scope and notation

The tables name real defining symbols and representative inspected callers. They
cover the proposed diagnostic/member/revision/relationship/dependency delivery
chains, not every Hashmarks method or every possible dynamic consumer. Shared
owners also serve other features. Absence of a direct call in the scoped search
is not proof that a Python symbol is globally unused.

The tables identify existing `CodeMap` mixin methods rather than separate
implementations. Test filenames are under `tests/`. Every row identifies an owning test
module; those tests are inventoried coverage, not an assertion that every module
was executed in the 147-test baseline.

### Diagnostic claims, identities and deltas

| Defining module / exact symbol | Concrete callers or binding | Evidence / schema / state | Owning tests; duplication risk; checkpoint |
| --- | --- | --- | --- |
| `hashmarks.codemap.diagnostic_observation.external_diagnostic_observation` | Static binding `RepositoryDeltaMixin.external_diagnostic_observation`; Python callers | Supplied rows and `RepositoryGenerationBinding`; external diagnostic observation v1; no history store | `test_diagnostic_member_evidence.py`; keep one normalizer; 02 |
| `hashmarks.codemap.diagnostic_source_revision.diagnostic_identity` | `external_diagnostic_observation`, `validated_diagnostic_endpoint`, `_validate_delta_conservation`, `RepositoryDeltaMixin._diagnostic_identity` | Hash of tool/rule/path/symbol/line/column/message, excluding source provenance | `test_diagnostic_source_revisions.py`; provenance identity is intentionally separate; 02, 05 |
| `hashmarks.codemap.diagnostic_source_revision.normalize_source_revision_claims` | Diagnostic constructor, endpoint claims, revision comparison, public validator, `scip_import_provenance` | Explicit scoped producer hashes; at most 32 revision members | `test_diagnostic_source_revisions.py`; shared qualification, not adapter-specific parsing; 02, 04 |
| `hashmarks.codemap.diagnostic_provenance.diagnostic_member_claims` | Constructor, endpoint/delta qualification, revision comparison; LSP/SCIP relationship adapters | Delegates to `normalize_source_provenance` and `normalize_collection_by_path`; both scoped and bounded; producer claims only | `test_diagnostic_member_evidence.py`; repeated validation must not become independent semantics; 02, 04 |
| `hashmarks.codemap.diagnostic_observation.diagnostic_endpoint_claims` | `validated_diagnostic_endpoint`, `diagnostic_observation_delta`, `_delta_endpoint_claims` | Canonical scoped revision/provenance/collection input projection | `test_diagnostic_member_evidence.py`; repeated endpoint normalization is an economics lead, not a proven bypass; 02, 08 |
| `hashmarks.codemap.diagnostic_observation.validated_diagnostic_endpoint` | Diagnostic delta; `repository_intelligence_validation._diagnostic_observation` | Checks endpoint schema/count/row identities; returns identity-keyed rows | `test_diagnostic_member_evidence.py`; duplicate input rows currently collapse in the map; 02 |
| `hashmarks.codemap.diagnostic_observation.diagnostic_observation_delta` | Static `RepositoryDeltaMixin` binding; `HashmarksMcpSurface._compare_native_evidence` | Diagnostic delta v1: separate diagnostic/source/provenance/collection/change axes; supplied endpoints only | `test_diagnostic_delta_validation.py`, `test_diagnostic_member_evidence.py`; canonical comparison owner; 05 |
| `hashmarks.codemap.diagnostic_observation.validated_diagnostic_delta` | `hashmarks.repository_intelligence_validation._diagnostic_delta` | Re-proves retained endpoint conservation and derived path/locality projections | `test_diagnostic_delta_validation.py`, `test_diagnostic_member_evidence.py`; intentional untrusted-packet boundary; 02, 05 |
| `hashmarks.codemap.diagnostic_path_delta.diagnostic_path_deltas` | Diagnostic delta producer and validator | Per-member conservation, completeness and optional qualified repository relationship annotations | `test_diagnostic_member_evidence.py`; shared pure projection re-used by validation; 05, 08 |
| `hashmarks.codemap.diagnostic_path_locality.diagnostic_path_locality` | Diagnostic delta producer and validator | Producer diagnostic paths intersect caller-reported changed paths; no causal inference | `test_diagnostic_path_locality.py`; separate responsibility from source movement; 05 |
| `hashmarks.codemap.repository_delta.RepositoryDeltaMixin.external_observation_freshness` | Python API; direct tests in `test_repository_intelligence_delta.py` | External observation freshness v1 compares repository/generation/change scope only | `test_repository_intelligence_delta.py`; its name must not imply producer/runtime freshness; 04 |

### Exact members, source lines and repository bindings

| Defining module / exact symbol | Concrete callers or binding | Evidence / schema / state | Owning tests; duplication risk; checkpoint |
| --- | --- | --- | --- |
| `hashmarks.codemap.repository_delta.RepositoryDeltaMixin._repository_member_observation` | `_bounded_source_observation`, binding `_observe_span` / `_observe_reference` / `_observe_binding`, correlation `_resolve_anchor` / `_resolve_module_only`, dependency `_dependency_repository_inputs`, declaration-provider reads | Shared path admission/visibility/symlink/index-revision owner; delegates stable reads to `_read_repository_member_source` and `FileDigestStore` | `test_repository_evidence_bindings.py`, `test_source_observation_evidence.py`; reuse instead of a new reader; 03, 04, 08 |
| `hashmarks.codemap.repository_delta.RepositoryDeltaMixin.source_observation` | `HashmarksMcpSurface.source_observation`, CLI `_source_observation_code`, Python | Source observation v1; exact member, revision, availability, freshness, requested line anchors and bounds | `test_source_observation_evidence.py`, `test_source_observation_cli.py`; one-member producer; 03, 04, 07 |
| `hashmarks.codemap.source_line_correspondence.source_line_anchors` | `RepositoryDeltaMixin._source_observation_from_bytes` | Exact physical line bytes from the same captured member, revision and uniqueness evidence | `test_diagnostic_source_line_correspondence.py`; no second file read; 03 |
| `hashmarks.codemap.source_line_correspondence.diagnostic_line_correspondence` | `diagnostic_observation_delta` | Compares both supplied source endpoints; source revision/generation/context must qualify before movement is supported | `test_diagnostic_source_line_correspondence.py`; candidate relocation alone is insufficient; 03, 05 |
| `hashmarks.codemap.diagnostic_source_revision.diagnostic_source_revision_evidence` | Static `RepositoryDeltaMixin` binding; Python consumers | Diagnostic source revision evidence v1; claimed vs observed bytes, source freshness, generation relation; no I/O or authentication | `test_diagnostic_source_revisions.py`, new correspondence module; separate bounded comparison authority; 03, 04 |
| `hashmarks.codemap.diagnostic_source_revision.validated_diagnostic_source_revision_evidence` | `hashmarks.repository_intelligence_validation._diagnostic_revision_evidence` | Revalidates retained comparison rows and summary | `test_diagnostic_source_revisions.py`; preserve unknown freshness even with matching bytes; 04 |
| `hashmarks.codemap.repository_evidence_bindings.RepositoryEvidenceBindingsMixin.repository_evidence_bindings` | `EvidenceCorrelationMixin.correlate_evidence`, `RepositoryDeclarationsMixin.repository_declarations`, MCP `_repository_binding_observation` | Bindings v1; delegates `_observe_binding` to exact member/span owner; output says `derived-not-persisted` | `test_repository_evidence_bindings.py`, `test_evidence_correlation.py`; opaque IDs, one observation owner; 03, 07 |
| `hashmarks.codemap.repository_evidence_bindings.RepositoryEvidenceBindingsMixin._observe_span` | `_observe_reference` | One stable member read; UTF-8 qualification, LF-preserving lines and domain-separated span hash | `test_repository_evidence_bindings.py`; member hash and span hash intentionally differ; 03, 04 |
| `hashmarks.codemap.repository_evidence_binding_delta.RepositoryEvidenceBindingDeltaMixin.repository_evidence_binding_delta` | `EvidenceCorrelationMixin.evidence_correlation_delta`, `RepositoryDeclarationsMixin.repository_declarations`, coverage `_validate_coverage_binding_delta`, MCP comparison | Binding delta v1; validates endpoint identities, compares repository/observer/member/relationship evidence separately | `test_repository_evidence_bindings.py`; observer change must not be relabeled as source edit; 05 |
| `hashmarks.codemap.repository_evidence_coverage.RepositoryEvidenceCoverageMixin.repository_evidence_coverage` | `HashmarksMcpSurface._repository_binding_coverage`; Python consumers | Coverage v1; explicit change-set authority and range precision; incomplete changes cannot prove outside scope | `test_repository_evidence_bindings.py`; keep separate from bounded presentation; 04, 05 |

### Correlation, ownership, verification and dependency evidence

| Defining module / exact symbol | Concrete callers or binding | Evidence / schema / state | Owning tests; duplication risk; checkpoint |
| --- | --- | --- | --- |
| `hashmarks.codemap.evidence_correlation.EvidenceCorrelationMixin.correlate_evidence` | `HashmarksMcpSurface.correlate_evidence`, `DependencyResolutionCorrelationMixin.dependency_evidence_correlation`, Python | Correlation v2; validated bounded bundles → existing repository bindings → qualified source equivalence and same-target correspondence; request-scoped | `test_evidence_correlation.py`, new correspondence module; no producer ingestion/history; 03, 06, 07 |
| `hashmarks.codemap.evidence_correlation.EvidenceCorrelationMixin.evidence_correlation_delta` | `correlate_evidence(previous_correlation=...)`; Python | Correlation delta v2; delegates repository differences to binding delta | `test_evidence_correlation.py`; does not re-resolve old anchors as current evidence; 05 |
| `hashmarks.codemap.evidence_correlation_replay.EvidenceCorrelationReplayMixin._validate_correlation_packet` | `evidence_correlation_delta` | Recomputes identity, definition and retained projections before comparison; no historical hydration | `test_evidence_correlation.py`; retain revalidation, not a parallel resolver; 02, 05 |
| `hashmarks.codemap.structural_locality.StructuralLocalityMixin.structural_locality` | MCP `structural_locality`, CLI `_structural_locality_code`; Python | Structural locality v1 or relationship mode; bounded source/caller evidence through qualified call/import owners | `test_structural_locality.py`, `test_negative_evidence_structural_locality_symbol_bounds.py`; incomplete candidate scope remains unresolved; 03, 06 |
| `hashmarks.codemap.task_action_owner_resolution.TaskActionOwnerResolutionMixin._task_action_resolve_owner` | `TaskActionProjectionMixin.task_action_map` | Existing explicit/literal/structural ownership qualification; not external-diagnostic diagnosis | `test_task_action_map.py`, `test_task_action_default_authority.py`; no new diagnostic owner selector; 03, 06 |
| `hashmarks.codemap.evidence_packet.TaskEvidencePacketMixin.task_evidence` | MCP `task_evidence`, CLI `_task_evidence_code`, service `_task_evidence_response`, post-change `_post_change_current_evidence` | Existing task-evidence modes; uses `task_action_map` and repository-bound verification evidence | `test_task_evidence.py`, `test_task_evidence_v5.py`, `test_task_evidence_initial.py`; no diagnostic-specific selector; 03, 07 |
| `hashmarks.codemap.verification_explanation.VerificationExplanationMixin.explain_verification_selection` | `RepositoryIntelligenceQueryMixin.repository_intelligence_query`, change intelligence, cross-repository evidence, freshness map | Existing `verification_relevance` and bounded candidate evidence; no sufficiency or execution claim | `test_repository_intelligence_query.py`; reuse selected-owner/verification authorities; 03, 06 |
| `hashmarks.codemap.dependency_resolution_evidence.DependencyResolutionEvidenceMixin.dependency_resolution_evidence` | `dependency_codemap`; Python | Producer-neutral dependency resolution v3, repository binding and exact source inputs; caller-claimed producer facts | `test_dependency_resolution_evidence.py`; syntax stays in adapters; 06 |
| `hashmarks.codemap.dependency_resolution_correlation.DependencyResolutionCorrelationMixin.dependency_import_correspondence` | Direct Python API and tests; no direct production invocation found in scoped call search | Qualified module-owner claims + repository import resolution; context/ambiguity preserved | `test_dependency_resolution_evidence.py`; not a resolver or execution-config winner; 06 |
| `hashmarks.codemap.dependency_resolution_correlation.DependencyResolutionCorrelationMixin.dependency_evidence_correlation` | Direct Python API and tests; calls existing `correlate_evidence` | Dependency evidence correlation v2; repository paths/source equivalence with exact dependency provenance | `test_dependency_resolution_evidence.py`; one underlying repository correlator; 06 |
| `hashmarks.codemap.dependency_resolution_evidence.DependencyResolutionEvidenceMixin.dependency_codemap` | MCP `dependency_codemap`, CLI `_dependency_codemap_code`; Python | Observation/explain/compare operation; delegates explanation and comparison to existing dependency mixins | `test_dependency_resolution_evidence.py`, `test_dependency_derivation_explain.py`; dispatch is not a second qualifier; 06, 07 |

### Freshness, storage and delivery boundaries

| Defining module / exact symbol | Concrete callers or binding | Evidence / schema / state | Owning tests; duplication risk; checkpoint |
| --- | --- | --- | --- |
| `hashmarks.codemap.indexing_lifecycle.IndexingLifecycleMixin._generation_status` | Source observations, repository bindings, verification explanation | CodeMap generation + identity observation/watch continuity; unknown preserved | `test_source_observation_evidence.py`, `test_repository_evidence_bindings.py`; repository state only; 04 |
| `hashmarks.codemap.evidence_verification.VerificationMixin._repository_packet_identity` / `_source_packet_identity` | Bindings, dependency evidence, verification explanation, change intelligence | Repository authority locator; source identity additionally binds CodeMap/identity generation and staleness | `test_repository_evidence_bindings.py`, `test_evidence_correlation.py`; repository locator alone is not member-byte identity; 04 |
| `hashmarks.codemap.evidence_freshness.EvidenceFreshnessMixin._record_evidence_snapshot` / `_evidence_fresh` | `EvidenceGraphMixin.import_scip` / `_enrich_project_graphs`; `_fresh_native_refs`, `StructuralLocalityMixin._scip_provider_freshness` and other qualified native readers | Manifest/generation qualification in workspace metadata; not external diagnostic freshness | `test_evidence_freshness_responsibility.py`; existing repository evidence lifetime owner; 04, 08 |
| `hashmarks.codemap.repository_intelligence_query.RepositoryIntelligenceQueryMixin.repository_intelligence_query` | MCP query, CLI `_repository_intelligence_query_code`, service/client; Python | Existing fixed surface dispatcher and `repository_query_response`; no new fact owner | `test_repository_intelligence_query.py`; reuse this facade for its supported surfaces; 07 |
| `hashmarks.codemap.query_router.route_query` | `FindEngineMixin.query_route` / `_find_context`, `OwnershipGraphMixin.task_entry_points`, context/task retrieval | Retrieval intent classification only | `test_codemap_query_router.py`; not the semantic query-envelope dispatcher; 07 |
| `hashmarks.operation_contract.operation_schema` / `validate_operation_response` | Core producers and transport convergence checks | Canonical operation/mode/schema mapping and response proof | `test_operation_contract.py`; do not copy schema selection into transports; 07, 08 |
| `hashmarks.repository_intelligence_validation.validate_repository_intelligence_evidence` | Supported top-level lazy export; external Python callers | Family-specific validation via existing diagnostic, revision and delta validators | `test_repository_intelligence_validation.py`; no consumer trust/authentication policy; 02, 07 |
| `hashmarks.evidence_presentation.present_repository_evidence` | `presentation_response`, `repository_query_response`, presentation conformance validator | Read-only projections of existing identities, qualifications and omission accounting | `test_evidence_presentation_contract.py`; presentation cannot strengthen evidence; 05, 07 |
| `hashmarks.mcp_surface.HashmarksMcpSurface._compare_native_evidence` / `evidence_comparison` | `mcp_server` registered comparison tool | Existing structural/binding/diagnostic/relationship comparison owners; bounded JSON and transport error translation | `test_diagnostic_member_evidence.py`, `test_mcp_surface.py`; mode dispatch, not independent comparison; 05, 07 |

`CodeMap.__init__` connects `WorkspaceMapStore` (`codemap.sqlite3`),
`FileDigestStore` (`identity.sqlite3`), `ArtifactStore` (content-addressed parsed
repository artifacts) and `ContextCache`. These are existing derived repository
stores. `decision_session` provides request-local reuse. The correlation,
diagnostic normalization and source-comparison owners above introduce no external
observation store. Retained external comparison packets are caller-owned inputs.
The process-local Python AST cache accelerates source analysis without becoming
repository identity or freshness authority.

## Existing surface coverage

| Operation | Python owner | CLI | MCP |
| --- | --- | --- | --- |
| Diagnostic normalization and revision comparison | `CodeMap` static bindings | No dedicated command | No dedicated normalization tool |
| Diagnostic endpoint comparison | `diagnostic_observation_delta` | No dedicated command | `evidence_comparison`, diagnostics mode |
| Exact source observations | `source_observation`, scoped/literal variants | `source-observation` | `source_observation` |
| Explicit repository bindings/coverage | `repository_evidence_bindings` / `repository_evidence_coverage` | No dedicated command | `repository_evidence` |
| External anchor correlation | `correlate_evidence` | No dedicated command | `correlate_evidence` |
| Structural locality | `structural_locality` / `structural_locality_delta` | `structural-locality` / `structural-locality-delta` | Locality and comparison modes |
| Task evidence | `task_evidence` | `task-evidence` | `task_evidence` |
| Dependency observation/explanation/comparison | `dependency_codemap` | `dependency-codemap` | `dependency_codemap` |
| Repository intelligence query | `repository_intelligence_query` | `repository-intelligence-query` | `repository_intelligence_query` |

CLI process entry stays in `hashmarks.cli.main`; repository commands stay in
`repository_cli`. MCP registration delegates through `HashmarksMcpSurface` to
the existing core. Surface parity means the same supported operation and mode,
options, repository state and bounds; it does not mean every Python operation
already has every transport. Unsupported combinations remain explicit gaps.

## Duplicate-path review and bounded investigation leads

No production path is removed in this census. No new production analyzer,
normalizer, source reader, selector, schema or transport is added.

| Inspected evidence | Classification / next step |
| --- | --- |
| `RepositoryDeltaMixin` static diagnostic bindings reference the defining functions | Delegation to the same implementation. Retain; do not count these as duplicate producers. |
| `hashmarks.codemap.repository_delta.RepositoryDeltaMixin._diagnostic_identity` wraps `diagnostic_identity`; no direct reference to the wrapper was found in the scoped source/test/script search | Call-chain cleanup candidate for 08. No independent fact implementation; check import/dynamic compatibility before removal. |
| `hashmarks.codemap.diagnostic_path_locality.indexed_diagnostic_rows` has no direct caller found in that same search; it builds a lenient identity-keyed map | Possible leftover parallel indexing helper for 08. Its permissive behavior differs from validated endpoint admission; no replacement or deletion is authorized by name similarity alone. |
| `diagnostic_observation_delta` normalizes endpoint claims, then endpoint validation normalizes them again; public validation also checks claims before validating the endpoint | Repeated work candidate. Measure before removing any check, preserving malformed-input failures and source/provenance semantics. |
| Constructor loops the supplied diagnostic sequence; provenance/revision maps have 32-member bounds. Correlation separately owns encoded request/packet limits | 02 contract gap to assess: explicit whole-envelope/diagnostic/string limits at the Python owner, not merely MCP transport limits. Do not invent a second validator or apply correlation limits by analogy without compatibility tests. |
| Two identical diagnostic rows produce `diagnostic_count=2`; comparing that packet with itself reports `before_count=1`, `unchanged_count=1` because comparison indexes by fact identity | Existing set-vs-occurrence behavior, reproduced locally. Freeze duplicate semantics and account for input occurrences in 02 before choosing rejection or deduplication. This census changes neither schema nor behavior. |
| Correlation replay and diagnostic public validation recompute identities/projections | Necessary integrity boundaries, not duplicate discovery implementations. Keep qualification at those untrusted-input boundaries. |

This is an inspected-scope review, not a global claim of zero duplication or
complete dynamic caller resolution. The two no-direct-caller results do not prove
global dead code. External correspondence remains independent per producer;
there is no transitive declaration graph, causal grouping or precedence winner.

## New local regression and follow-on sequence

`test_diagnostic_repository_correspondence.py` generates two Python modules with
the same `handle_request` symbol. Its first test retains both candidates, unknown
source equivalence and inadmissible negative external evidence. Its second test
captures a real member revision, edits that member and reconciles CodeMap. The
path still resolves, but the old producer revision mismatches current bytes;
the diagnostic revision comparison preserves both revisions and generation
relations. The fixture uses explicit temporary state/artifact paths, runs no
target code, and requires no external files or service.

Run the additive ring independently of the historical baseline:

```bash
XDG_CACHE_HOME=/tmp/hashmarks-plan-cache \
UV_CACHE_DIR=/tmp/hashmarks-plan-uv \
uv run --frozen --offline --no-sync --group test \
python -m pytest -q -p no:cacheprovider --tb=short \
  --junitxml=dist/hm-obs/correspondence.xml \
  tests/test_diagnostic_repository_correspondence.py \
  tests/test_diagnostic_source_revisions.py \
  tests/test_diagnostic_source_line_correspondence.py
```

| Bundle / checkpoints | Existing owner and next bounded work | Acceptance selection, in addition to original baseline |
| --- | --- | --- |
| A: 01 census, then 02 contract | Diagnostic constructor, provenance, endpoint and public validators. Resolve demonstrated envelope-bound and duplicate-accounting leads with compatibility fixtures. | New correspondence module; `test_diagnostic_source_revisions.py`, `test_diagnostic_path_locality.py`; additive malformed, oversized and duplicate envelope regressions. |
| B: 03 correspondence, 04 freshness, 05 deltas | Member/source/line owners, diagnostic and binding deltas. Extend only missing cases for rename/move/delete, codec/line endings, partial snapshots and observer-only changes. | `test_diagnostic_source_line_correspondence.py`, `test_diagnostic_source_revisions.py`, `test_source_observation_evidence.py`, `test_repository_evidence_bindings.py`, `test_backend_changed_line_evidence.py`, `test_backend_evidence_navigation.py`, `test_repository_intelligence_delta.py`. |
| C: 06 relationships, 07 delivery | Structural locality, existing task owner/verifier, dependency correspondence and existing transport facades. Preserve import identity, contexts and alternatives. No new tool is presumed necessary. | `test_structural_locality.py`, `test_negative_evidence_structural_locality_symbol_bounds.py`, `test_task_action_map.py`, `test_task_evidence.py`, `test_task_evidence_candidate_verification.py`, `test_dependency_resolution_evidence.py`, `test_dependency_derivation_explain.py`, `test_repository_intelligence_query.py`, `test_operation_contract.py`, `test_evidence_presentation_contract.py`, `test_source_observation_cli.py`. |
| D: 08 convergence, 09 qualification | Remove only reproduced redundant responsibilities with caller proof. Add focused guard mutations for the demonstrated failure, plus local fixture/replay/parity and comparable read-cost measurements. | Above owning suites plus `test_evidence_freshness_responsibility.py`, `test_semantic_ownership_architecture.py`; local generated held-out cases with expected owner/unknown/ambiguity frozen before measurement. |

An already-correct behavior gets evidence-backed closure rather than forced code
movement. Responsibility cleanup is subject to
[RESPONSIBILITY_REFACTORING](../maintainers/RESPONSIBILITY_REFACTORING.md).
Ranking gains require comparable fixture populations and zero new false unique
owners, false absence or authority upgrades. This census makes no performance or
relevance improvement claim.

Before handoff run `make agent-finish` and `make agent-preflight`; subsequent
production changes also run focused owner tests and named bounded development
batches. Optional capabilities stay separately reported as skipped/NOT_PROVEN.
No source-only result certifies a producer runtime. Source rollback uses the
consumer's normal Git workflow; this change introduces no persistent-state
migration or runtime recovery machinery.

## Census validation receipt

The original baseline and additive ring cover **200 distinct tests**, all passing
with zero failures/errors/skips; two are new regression tests. The five original
test files, `pyproject.toml` and `uv.lock` retain their pre-edit hashes.

- `make agent-preflight`: canonical Ruff formatting/checks pass; current complexity
  debt and production file-size excess are both zero.
- Focused `ty check tests/test_diagnostic_repository_correspondence.py`: passes.
- Focused `pyright tests/test_diagnostic_repository_correspondence.py`: zero
  errors/warnings. Both use `uv run --frozen --offline --no-sync --group typing`
  with the same cache environment as the baseline.
- Defining-symbol, named-test-file and normative-link checks pass using repository
  source ASTs; this verifies locators, not dynamic dispatch completeness.

No production method was migrated or removed by the census stage. The
HM-OBS-02..09 descriptions above preserve its original prospective sequence;
see the linked implementation receipt for their subsequent changes and proof. No full-suite, external
runtime, optional native-capability or release certification is claimed.
