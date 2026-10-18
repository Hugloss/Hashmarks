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

`suite.json` and `grader.json` now contain twelve source-reviewed workflows over
the three repositories: explicit AsyncAPI route-call syntax, included-stream
handler annotations, Annotated handler input/decorator/body observations, and
exact source calls/arguments involved in the other genuine changes.
They reuse the existing backend workflow runner, declaration/boundary surfaces,
source admission and artifact-bound pure graders. Exact source references are
frozen independently of observer output. All capability review flags remain
false. These selected static slices do not establish full handler semantics,
runtime wiring, registration, branch behavior or sufficient verification.

Run the existing materializer with this suite and the three caller-selected
repository checkouts, then pass its `sources.json` to the existing runner:

```sh
uv run --frozen python -m scripts.repository_evaluation.materialize_backend \
  --repository fastapi=/path/to/fastapi \
  --repository litestar=/path/to/litestar \
  --repository faststream=/path/to/faststream \
  --suite benchmarks/repository_evaluation/manifests/backend-handler-v1/suite.json \
  --output-dir .hashmarks/backend-e2e/handlers

uv run --frozen python -m scripts.repository_evaluation.run_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-handler-v1/suite.json \
  --sources-file .hashmarks/backend-e2e/handlers/sources.json \
  --output-dir .hashmarks/backend-e2e/handler-qualification
```

Missing transports, semantic slices or adversaries remain incomplete.

Next, complete review of causal ownership and input/return/branch coverage beyond
these bounded source facts, then qualify the population through API/CLI/official MCP,
current native producers, source changes, staleness, reopen and semantic
adversaries. Reusing a problem for another capability adds no distinct breadth.
