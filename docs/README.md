# Hashmarks repository intelligence documentation

Hashmarks keeps **current, maintained documentation** in the live repository. Superseded plans, handoffs, phase receipts, and old status ledgers belong to Git/PR history rather than the product documentation tree.

## Start here

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, CodeMap workflow, CLI, Python API, cache/state basics.
- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — architecture and authority model.
- [`reference/STATE_AND_SEMANTIC_OWNERS.md`](reference/STATE_AND_SEMANTIC_OWNERS.md) — canonical state families, semantic owners, and reuse-before-new-owner rules.
- [`reference/REPOSITORY_EVIDENCE_BINDINGS.md`](reference/REPOSITORY_EVIDENCE_BINDINGS.md) — repository evidence bindings and change semantics.
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — normative feature-admission contract.
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — normative correctness, freshness, and authority guarantees.
- [`reference/API_STABILITY.md`](reference/API_STABILITY.md) — supported Python/CLI surface and pre-1.0 compatibility policy.
- [`../CHANGELOG.md`](../CHANGELOG.md) — public release history only.

## Maintainers

- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — module ownership and request-flow guide.
- [`maintainers/RESPONSIBILITY_REFACTORING.md`](maintainers/RESPONSIBILITY_REFACTORING.md) — responsibility-first refactoring policy.
- [`maintainers/RELEASING.md`](maintainers/RELEASING.md) — current release procedure.

## Integration

- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — current Hashmarks ↔ Oh-Goon evidence/authority boundary.
- [`integration/MCP.md`](integration/MCP.md) — local read-only MCP server, freshness behavior, and host configuration.

## Qualification

- [`qualification/REPOSITORY_QUALITY.md`](qualification/REPOSITORY_QUALITY.md) — repository-quality qualification semantics.
- [`qualification/TEST_RUNTIME_ECONOMICS.md`](qualification/TEST_RUNTIME_ECONOMICS.md) — test-proof scope and runtime-economics guidance.

Development-tool dependencies and configuration are owned by `pyproject.toml` and the committed `uv.lock`; contributor commands are documented in [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md).

Historical development material is intentionally recovered from Git commits, merged pull requests, and release history when needed. It is not duplicated as a maintained documentation surface.
