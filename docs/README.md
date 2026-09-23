# Hashmarks repository intelligence documentation

This is the single catalog for the current maintained documentation in `docs/`.

## Getting started

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, CodeMap workflow, CLI, Python API, cache/state basics.

## Reference

- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — architecture and authority model.
- [`reference/API_STABILITY.md`](reference/API_STABILITY.md) — supported Python/CLI surface and pre-1.0 compatibility policy.
- [`reference/EVIDENCE_CORRELATION.md`](reference/EVIDENCE_CORRELATION.md) — bounded external-observation correlation and authority limits.
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — normative correctness, freshness, and authority guarantees.
- [`reference/OBSERVER_DELTA.md`](reference/OBSERVER_DELTA.md) — observer/delta ownership and change semantics.
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — normative feature-admission and ownership contract.
- [`reference/REPOSITORY_EVIDENCE_BINDINGS.md`](reference/REPOSITORY_EVIDENCE_BINDINGS.md) — repository evidence bindings and change semantics.
- [`reference/STATE_AND_SEMANTIC_OWNERS.md`](reference/STATE_AND_SEMANTIC_OWNERS.md) — canonical state families, semantic owners, and reuse-before-new-owner rules.
- [`reference/STRUCTURAL_LOCALITY.md`](reference/STRUCTURAL_LOCALITY.md) — bounded structural-locality evidence for repository symbols.

## Integration

- [`integration/MCP.md`](integration/MCP.md) — local read-only MCP server, freshness behavior, and host configuration.
- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — Hashmarks ↔ Oh-Goon evidence/authority boundary.

## Maintainers

- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — module ownership and request-flow guide.
- [`maintainers/RELEASING.md`](maintainers/RELEASING.md) — current release procedure.
- [`maintainers/RESPONSIBILITY_REFACTORING.md`](maintainers/RESPONSIBILITY_REFACTORING.md) — responsibility-first refactoring policy.

## Qualification

- [`qualification/REPOSITORY_QUALITY.md`](qualification/REPOSITORY_QUALITY.md) — repository-quality qualification semantics.
- [`qualification/TEST_RUNTIME_ECONOMICS.md`](qualification/TEST_RUNTIME_ECONOMICS.md) — test-proof scope and runtime-economics guidance.

Development-tool dependencies and configuration are owned by `pyproject.toml` and the committed `uv.lock`; contributor commands live in [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md). Public release history lives in [`CHANGELOG.md`](../CHANGELOG.md).
