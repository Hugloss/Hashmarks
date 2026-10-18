# Genuine handler source intake

`source-catalog.json` pins twelve distinct upstream changes across FastAPI,
Litestar and FastStream, with exact before/after commits and repository-content
identities. Selected owner/test file hashes are source-input identity checks;
candidate paths are not an independently reviewed owner or relevance oracle.

This catalog is **INCOMPLETE** and is not part of the active campaign. Its
semantic and capability review flags remain false. It does not promote any
capability, relax a gate, or replace required native/runtime/transport witnesses.

Materialize the caller-selected commits from the listed upstream repositories
as exact Git archives. Recompute `repository_content_identity` for every tree
and verify selected-file hashes before using its source. Source archives and
exploratory AST/span observations are retained locally under
`.hashmarks/canonical-component-rewrite/cr14-handler-source-intake/`.

Three nominated test files exist only after their changes. Existing before-test
surfaces have been inspected separately, but are relevance candidates only:
`tests/test_custom_route_class.py`, `tests/test_sse.py`, and
`tests/asgi/testcase.py`. They do not establish sufficient regression coverage.

Next, review exact causal owners and test declarations, freeze bounded
handler/decorator/input/return/branch facts with byte-exact source references,
and declare unsupported or dynamic facts explicitly. Then integrate with the
existing backend evaluator and qualify API/CLI/official MCP, current native
producers, source changes, staleness, reopen and semantic adversaries. Reusing
an existing problem for another capability adds no distinct-problem breadth.
