# Responsibility vocabulary audit — v0.11.21 development

This audit classifies execution/authority-shaped cross-module vocabulary by ownership rather than globally replacing words.

- `authority_ownership_graph` and `scoped_authority`: v0.11 compatibility method/schema vocabulary. Modern owners are `repository_ownership_graph` and `repository_instruction_scope`; legacy methods delegate.
- `authority_file_rows`: compatibility store spelling. Modern query code uses `repository_instruction_file_rows`; legacy spelling delegates.
- `_authority_add_*` ownership-graph helpers: internal repository-ownership implementation, renamed `_ownership_add_*`; no serialized contract impact.
- `ExecutionIdentity`, `resolve_execution_identity`, `ActionCache`, `ActionResult`, `ExecutionCache`, `IdentityEngine`: genuine historical runtime-shaped compatibility surfaces; classified and contained by `../PREPUBLIC_BOUNDARY_DEBT.md` and G53/G59. Do not cosmetically rename.
- authority cue strings and serialized fields/schemas: repository search vocabulary or stable v0.11 compatibility data. Preserve where changing spelling would change retrieval semantics or wire compatibility.
- execution/certification/admission descriptions in interoperability metadata/docs: legitimate external-boundary descriptions; they transfer no authority.

Modern CodeMap/repository-intelligence code must use repository/evidence vocabulary for owned semantics and must not acquire new dependencies on compatibility-only execution modules.
