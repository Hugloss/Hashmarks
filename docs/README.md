# Hashmarks repository intelligence documentation

This is the single catalog for the current maintained documentation in `docs/`.

## Getting started

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, CodeMap workflow, CLI, Python API, cache/state basics.

## Reference

- [`reference/AGENT_NATIVE_EVIDENCE.md`](reference/AGENT_NATIVE_EVIDENCE.md) — agent-facing typed evidence and bounded MCP exposure.
- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — architecture and authority model.
- [`reference/API_STABILITY.md`](reference/API_STABILITY.md) — supported Python/CLI surface and pre-1.0 compatibility policy.
- [`reference/EVIDENCE_CORRELATION.md`](reference/EVIDENCE_CORRELATION.md) — bounded external-observation correlation and authority limits.
- [`reference/FILESYSTEM_LIFECYCLE_EVIDENCE.md`](reference/FILESYSTEM_LIFECYCLE_EVIDENCE.md) — qualified Python filesystem checks, source-reference flow, protection syntax and uncertainty.
- [`reference/DEPENDENCY_EVIDENCE.md`](reference/DEPENDENCY_EVIDENCE.md) — producer-neutral dependency evidence, adapter boundaries, semantic authorities, and coverage rules.
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — normative correctness, freshness, and authority guarantees.
- [`reference/INPUT_OBSERVATIONS.md`](reference/INPUT_OBSERVATIONS.md) — coherent selected-input identity, recursive inventory, explicit counts, and local observation bounds.
- [`reference/MAKE_SHELL_EVIDENCE.md`](reference/MAKE_SHELL_EVIDENCE.md) — explicitly selected Make/shell declarations, invocation syntax, and unresolved expansion.
- [`reference/OBSERVER_DELTA.md`](reference/OBSERVER_DELTA.md) — observer/delta ownership and change semantics.
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — normative feature-admission and ownership contract.
- [`reference/PYTHON_UV_MANIFEST_EVIDENCE.md`](reference/PYTHON_UV_MANIFEST_EVIDENCE.md) — authored Python dependencies, scripts, uv sources, and static workspace candidates.
- [`reference/REPOSITORY_EVIDENCE_BINDINGS.md`](reference/REPOSITORY_EVIDENCE_BINDINGS.md) — repository evidence bindings and change semantics.
- [`reference/REPOSITORY_DECLARATIONS.md`](reference/REPOSITORY_DECLARATIONS.md) — cross-artifact declaration correspondence, exact evidence, ambiguity, qualified absence, and factual deltas.
- [`reference/SOURCE_OBSERVATION.md`](reference/SOURCE_OBSERVATION.md) — bounded source occurrences, observable scope, diagnostic correspondence, and source-shape evidence.
- [`reference/SOURCE_RANGE_RECEIPTS.md`](reference/SOURCE_RANGE_RECEIPTS.md) — exact original byte ranges, member revision binding, and canonical freshness.
- [`reference/STATE_AND_SEMANTIC_OWNERS.md`](reference/STATE_AND_SEMANTIC_OWNERS.md) — canonical state families, semantic owners, and reuse-before-new-owner rules.
- [`reference/STRUCTURAL_LOCALITY.md`](reference/STRUCTURAL_LOCALITY.md) — bounded structural-locality evidence for repository symbols.
- [`reference/STATIC_INTERFACE_EVIDENCE.md`](reference/STATIC_INTERFACE_EVIDENCE.md) — selected static Python route/tool syntax and bounded SCIP symbol evidence.
- [`reference/VERIFICATION_MEMBERSHIP_HANDOFF.md`](reference/VERIFICATION_MEMBERSHIP_HANDOFF.md) — source-bound supplied native membership and public retained-packet validation.

## Integration

- [`integration/MCP.md`](integration/MCP.md) — local read-only MCP server, freshness behavior, and host configuration.
- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — Hashmarks ↔ Oh-Goon evidence/authority boundary.
- [`integration/STANDALONE_CONSUMERS.md`](integration/STANDALONE_CONSUMERS.md) — installed-package consumer entry points, identity/inventory, membership handoff, declarations, and byte receipts.

## Maintainers

- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — module ownership and request-flow guide.
- [`maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md`](maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md) — implementation plan for traceable derived authority and cheap endpoint comparison without historical-archive or Git-lifecycle ownership.
- [`maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md`](maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md) — accepted decision for semantic-subject/declaration/observation identity without branch, merge, mutation, or history ownership.
- [`maintainers/RELEASING.md`](maintainers/RELEASING.md) — current release procedure.
- [`maintainers/RESPONSIBILITY_REFACTORING.md`](maintainers/RESPONSIBILITY_REFACTORING.md) — responsibility-first refactoring policy.

## Plans

- [`plans/STABILIZATION_PLAN.md`](plans/STABILIZATION_PLAN.md) — completed finite delivery: canonical ownership, current typing/regressions, representative public evidence and an advisory response-size target.
- [`plans/CANONICAL_COMPONENT_REWRITE_PLAN.md`](plans/CANONICAL_COMPONENT_REWRITE_PLAN.md) — component rewrite design/history and separately deferred broad 5/5 qualification; stabilization is the active finish line.
- [`plans/CANONICAL_OWNER_CONSOLIDATION_PLAN.md`](plans/CANONICAL_OWNER_CONSOLIDATION_PLAN.md) — superseded bounded owner-consolidation plan and source-binding/cache repair background.
- [`plans/HM_OBS_REPOSITORY_EVIDENCE_OWNER_CENSUS.md`](plans/HM_OBS_REPOSITORY_EVIDENCE_OWNER_CENSUS.md) — diagnostic-to-repository canonical owners, focused baseline, local regressions and standalone follow-on bundles.
- [`plans/HASHMARKS_TOCTOU_EVIDENCE_DISCOVERY_PLAN.md`](plans/HASHMARKS_TOCTOU_EVIDENCE_DISCOVERY_PLAN.md) — filesystem check/use implementation and required native/reference/external qualification.
- [`plans/COMPETITOR_EVIDENCE_CONSOLIDATED.md`](plans/COMPETITOR_EVIDENCE_CONSOLIDATED.md) — single-PR admission and implementation checklist for competitor-inspired repository evidence.
- [`plans/COMPETITOR_EVIDENCE_FOLLOWUP.md`](plans/COMPETITOR_EVIDENCE_FOLLOWUP.md) — post-#415 checkpoint boundaries, opt-in static handler syntax and deferred provider/measurement work.

## Qualification

- [`qualification/STABILIZATION_REPORT.md`](qualification/STABILIZATION_REPORT.md) — current stabilization evidence, source identity, complete checks and retained limitations; broad 5/5 research remains incomplete.
- [`qualification/DIAGNOSTIC_CORRESPONDENCE.md`](qualification/DIAGNOSTIC_CORRESPONDENCE.md) — standalone HM-OBS-01..09 implementation, local fixture replay, contract changes and comparable read economics.
- [`qualification/OPTIONAL_MCP_TESTS.md`](qualification/OPTIONAL_MCP_TESTS.md) — SDK-absent CI execution, preserved CLI coverage, SDK-present checks and inventory-independent economics assertions.

- [`qualification/AGENT_EVIDENCE_FORMATS.md`](qualification/AGENT_EVIDENCE_FORMATS.md) — paired evidence-presentation export and external agent grading.
- [`qualification/BACKEND_E2E.md`](qualification/BACKEND_E2E.md) — genuine backend revision workflows, source oracles and all-capability qualification accounting.
- [`qualification/BACKEND_E2E_CAMPAIGN.md`](qualification/BACKEND_E2E_CAMPAIGN.md) — frozen capability membership, current measurements and remaining backend qualification work.
- [`qualification/BACKEND_E2E_REMAINING_PLAN.md`](qualification/BACKEND_E2E_REMAINING_PLAN.md) — deferred broad backend research backlog and retained checkpoints; these scores do not block stabilization.
- [`qualification/REPOSITORY_QUALITY.md`](qualification/REPOSITORY_QUALITY.md) — repository-quality qualification semantics.
- [`qualification/TEST_RUNTIME_ECONOMICS.md`](qualification/TEST_RUNTIME_ECONOMICS.md) — test-proof scope and runtime-economics guidance.

Development-tool dependencies and configuration are owned by `pyproject.toml` and the committed `uv.lock`; contributor commands live in [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md). Public release history lives in [`CHANGELOG.md`](../CHANGELOG.md).
