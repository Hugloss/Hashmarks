# Hashmarks repository intelligence documentation

Hashmarks documentation is split into **public/current contracts** and **historical development evidence**. Current product behavior should be understood from the first group; historical phase notes are evidence, not product authority.

## Start here

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, CodeMap workflow, CLI, Python API, cache/state basics.
- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — architecture and authority model.
- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — implementation ownership map and request-flow guide for maintainers.
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — normative feature-admission contract; read this before proposing a new capability.
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — normative correctness/freshness/authority guarantees.
- [`reference/API_STABILITY.md`](reference/API_STABILITY.md) — supported Python/CLI surface and pre-1.0 compatibility policy.
- [`../CHANGELOG.md`](../CHANGELOG.md) — concise user-facing release history.

## Maintainers

- [`maintainers/README.md`](maintainers/README.md) — current implementation-navigation docs and their relationship to product contracts/history.
- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — CodeMap module ownership, common request flows, and debugging entry points.

## Integration

- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — current Hashmarks ↔ Oh-Goon evidence/authority boundary.
- [`integration/MCP.md`](integration/MCP.md) — Hashmarks local read-only MCP server for coding agents, codebase search/repository context tools, freshness behavior, and Claude Code/Codex/OpenCode/Pi configuration.

## Qualification

- [`qualification/TEST_RUNTIME_ECONOMICS.md`](qualification/TEST_RUNTIME_ECONOMICS.md) — test-proof scope and runtime-economics guidance.

Development-tool dependencies and configuration are owned directly by `pyproject.toml`; contributor commands are documented in [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md).

## Historical development record

The full GitHub source repository retains non-normative development history under `docs/development/`, including handoffs, benchmark evidence, audits, reviews, and historical invariant ledgers. That material is characterization evidence, not active roadmap work. The archaeology is intentionally excluded from the PyPI source distribution and must not override current files under `reference/`, `integration/`, or the root `README.md`.

Repository-root Markdown is intentionally limited to public release-facing documents such as the landing page, changelog, and contributor-agent guardrail. GitHub-specific community documents live under `.github/`.
