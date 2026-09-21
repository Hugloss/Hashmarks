# Public API and stability policy

Hashmarks is pre-1.0, but the first public release still needs an explicit contract so implementation history does not accidentally become API.

## What is public

The supported Python API is:

1. names exported by `hashmarks.__all__`, including the lazily exposed `CodeMap`;
2. behavior documented in the root `README.md`, `docs/GETTING_STARTED.md`, and current files under `docs/reference/`;
3. CLI commands documented in the current README/getting-started documentation, including the optional local `hashmarks mcp` stdio surface;
4. explicitly versioned producer/consumer schemas whose validators are part of the documented repository-evidence contract.

The documented `CodeMap.repository_evidence_bindings()`, `repository_evidence_binding_delta()`, and `repository_evidence_coverage()` methods are supported Python API through the exported `CodeMap` class. Their current schemas are `hashmarks.repository-evidence-bindings.v1`, `hashmarks.repository-evidence-binding-delta.v1`, and `hashmarks.repository-evidence-coverage.v1`; see [`REPOSITORY_EVIDENCE_BINDINGS.md`](REPOSITORY_EVIDENCE_BINDINGS.md).

The documented `CodeMap.correlate_evidence()` and `evidence_correlation_delta()` methods are also supported Python API. Their schemas are `hashmarks.evidence-correlation.v1` and `hashmarks.evidence-correlation-delta.v1`; see [`EVIDENCE_CORRELATION.md`](EVIDENCE_CORRELATION.md). Correlation remains a projection over existing repository evidence authorities and does not grant causal or action authority.

`CodeMap.task_evidence()` is the current role-separated task-evidence API. Its schema is `hashmarks.task-evidence.v2`: bounded retrieval, explicit-target evidence, ownership, verification, related evidence, freshness and provenance are distinct authority domains. The unpublished v1 task-evidence shape is not retained as a compatibility reader or alias.

Importable implementation submodules under `hashmarks.*` are **not automatically public** merely because Python allows importing them. Internal helpers, storage classes, parsers, adapters, and mixins may change without compatibility guarantees unless a current public document explicitly promotes them into the contract.

Development material under `scripts/agent_evaluation/`, `benchmarks/agent_evaluation/`, `tests/`, and `docs/development/` is measurement/evidence infrastructure, not installed product API.

## Pre-1.0 contract evolution

For the `0.x` series:

- Hashmarks carries one current documented Python/CLI surface before the first public release; obsolete unpublished names are removed rather than aliased.
- generated local databases/caches are disposable and may be rebuilt when their current shape changes; no migration/backward-reader obligation exists unless a future explicit requirement introduces one.
- serialized repository-evidence contracts use explicit schema identities and validators; obsolete development/evaluation schema readers are removed instead of normalized.
- implementation details and development evaluation formats are not compatibility commitments.

Current client/daemon protocol checks remain fail-closed safety validation: a mixed incompatible runtime is rejected rather than adapted.

## Authority stability

Compatibility must never weaken Hashmarks' authority model. In particular:

- cached/incremental evidence may not become stronger than current reconciled repository truth;
- compatibility must not turn consumer workflow state into repository authority;
- interoperability may transfer evidence, never execution or solution authority;
- fail-closed freshness and provenance rules take precedence over preserving an obsolete convenience API.

See [`PRODUCT_BOUNDARY.md`](PRODUCT_BOUNDARY.md) and [`INVARIANTS.md`](INVARIANTS.md).
