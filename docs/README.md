# Hashmarks repository intelligence documentation

This is the single catalog for the current maintained documentation in `docs/`.

## Getting started

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, CodeMap workflow, CLI, Python API, cache/state basics.

## Reference

- [`reference/AGENT_NATIVE_EVIDENCE.md`](reference/AGENT_NATIVE_EVIDENCE.md) — agent-facing typed evidence and bounded MCP exposure.
- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — architecture and authority model.
- [`reference/API_STABILITY.md`](reference/API_STABILITY.md) — supported Python/CLI surface and pre-1.0 compatibility policy.
- [`reference/EVIDENCE_CORRELATION.md`](reference/EVIDENCE_CORRELATION.md) — bounded external-observation correlation and authority limits.
- [`reference/DEPENDENCY_EVIDENCE.md`](reference/DEPENDENCY_EVIDENCE.md) — producer-neutral dependency evidence, adapter boundaries, semantic authorities, and coverage rules.
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — normative correctness, freshness, and authority guarantees.
- [`reference/OBSERVER_DELTA.md`](reference/OBSERVER_DELTA.md) — observer/delta ownership and change semantics.
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — normative feature-admission and ownership contract.
- [`reference/REPOSITORY_EVIDENCE_BINDINGS.md`](reference/REPOSITORY_EVIDENCE_BINDINGS.md) — repository evidence bindings and change semantics.
- [`reference/REPOSITORY_DECLARATIONS.md`](reference/REPOSITORY_DECLARATIONS.md) — cross-artifact declaration correspondence, exact evidence, ambiguity, qualified absence, and factual deltas.
- [`reference/SOURCE_OBSERVATION.md`](reference/SOURCE_OBSERVATION.md) — bounded source occurrences, observable scope, diagnostic correspondence, and source-shape evidence.
- [`reference/STATE_AND_SEMANTIC_OWNERS.md`](reference/STATE_AND_SEMANTIC_OWNERS.md) — canonical state families, semantic owners, and reuse-before-new-owner rules.
- [`reference/STRUCTURAL_LOCALITY.md`](reference/STRUCTURAL_LOCALITY.md) — bounded structural-locality evidence for repository symbols.

## Integration

- [`integration/MCP.md`](integration/MCP.md) — local read-only MCP server, freshness behavior, and host configuration.
- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — Hashmarks ↔ Oh-Goon evidence/authority boundary.

## Maintainers

- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — module ownership and request-flow guide.
- [`maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md`](maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md) — implementation plan for traceable derived authority and cheap endpoint comparison without historical-archive or Git-lifecycle ownership.
- [`maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md`](maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md) — accepted decision for semantic-subject/declaration/observation identity without branch, merge, mutation, or history ownership.
- [`maintainers/RELEASING.md`](maintainers/RELEASING.md) — current release procedure.
- [`maintainers/RESPONSIBILITY_REFACTORING.md`](maintainers/RESPONSIBILITY_REFACTORING.md) — responsibility-first refactoring policy.

## Qualification

- [`qualification/AGENT_EVIDENCE_FORMATS.md`](qualification/AGENT_EVIDENCE_FORMATS.md) — paired evidence-presentation export and external agent grading.
- [`qualification/REPOSITORY_QUALITY.md`](qualification/REPOSITORY_QUALITY.md) — repository-quality qualification semantics.
- [`qualification/TEST_RUNTIME_ECONOMICS.md`](qualification/TEST_RUNTIME_ECONOMICS.md) — test-proof scope and runtime-economics guidance.

Development-tool dependencies and configuration are owned by `pyproject.toml` and the committed `uv.lock`; contributor commands live in [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md). Public release history lives in [`CHANGELOG.md`](../CHANGELOG.md).
