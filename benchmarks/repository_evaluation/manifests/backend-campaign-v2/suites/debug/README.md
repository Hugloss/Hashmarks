# Debugging source catalog — partial intake

This catalog admits four distinct genuine upstream problems in SQLAlchemy, with
eight exact before/after source archives. Two reuse existing campaign problems;
the other two add distinct global problems. Capability 4 still needs at least
eight more problems and two more repositories. The initial remaining pool is
four problems each from databases and Litestar. Independent capability and
display/adversarial review remains incomplete.
All capability-4 review flags are false. This catalog establishes no 5/5 rating.

| Problem | Genuine invocation and transition | Qualification limit |
| --- | --- | --- |
| [Logging token reset](https://github.com/sqlalchemy/sqlalchemy/commit/975ffa7d77ee3bbf5afd470bc93a1bc1d7f88df4) | SQLite connection token set once, reset twice: AttributeError before, successful query after | Four captured repository frames; a successful after control provides no frame or repository-absence proof |
| [Aggregate strings](https://github.com/sqlalchemy/sqlalchemy/commit/7e80ddda2a6b820860f8fc1fa8213b85e2819d2b) | `str(select(func.aggregate_strings(...)))`: TypeError before, successful rendering after | Fourteen frames, including one unsupported comprehension; the failure stops at the caller before entering the missing-argument callee |
| [Custom metadata warning](https://github.com/sqlalchemy/sqlalchemy/commit/6165193fb3f469471ac20b16fa394c103bb3a090) | Declarative class supplies its own MetaData with warnings treated as errors: SAWarning before, retained metadata after | Six before frames; the after success control supplies no correspondence units |
| [Forward reference diagnostic](https://github.com/sqlalchemy/sqlalchemy/commit/5503ac27c412cf99baa838db98bf10a8f1e26f16) | Unquoted undefined declarative annotation under Python 3.14.7: container TypeError before, intentional MappedAnnotationError after | Ten before frames across three displayed exceptions and six after frames; the after exception is an intended diagnostic, not successful execution |

`runtime_observations` contain externally acquired captures and a nominated
bundle identity. They are inputs, not requests to execute a backend scenario.
The product sees only bounded frame claims. `runtime_oracles` independently bind
runtime scope/code-first-line to pinned source declarations, with frozen positive
and invalidated-revision checks. Every captured frame appears in
`debug_frame_units`; unsupported frames remain metric misses. Copies on different
transports never increase frame breadth.

Both before/after task profiles run through API, CLI and the official MCP SDK.
Runtime claims with frames also run through all surfaces and presentations, in
qualified and deliberately invalidated variants. Retained-byte regrading checks
the original capture and request identities, exact frame membership, repository
source equivalence, declaration identity, public authority/uncertainty fields,
canonical packet parity and presentation conformance. It never runs the backend,
the observer or a native producer. Source and native capture freshness remain
separate dimensions.

All four problems now have fresh captures from the finite development producer
`scripts.repository_evaluation.capture_backend_failure`, including exact producer,
observer, evaluator and Python identities. The Python 3.14 specimen uses native
unquoted annotation semantics. Every displayed ordinary cause/context is retained;
suppressed context does not add frames. The earlier original and one-off captures
remain historical. This catalog replays supplied observations. Source-only
oracle construction is not independent
capability review. The independently scoped native LSP/SCIP ring still requires
fresh acquisition and its own artifact/source verification.

Source-only review froze additional aggregate-strings task scope:

- The fix adds `StrSQLCompiler.visit_aggregate_strings_func` as well as changing
  the base `SQLCompiler` signature. The task checks now require disclosure of
  that new override; the independently nominated native targets stay separate.
- The after labels preserve the separate intentional DefaultDialect CompileError
  guard and add the actual successful string-rendering regression,
  `CompileTest.test_aggregate_strings_str`.
- `SQLCompiler.visit_function` is the innermost actual TypeError frame. Do not
  change its identity to the callee named in the exception or infer a complete
  caller/callee path.

These review additions are recorded independently at
`.hashmarks/backend-e2e/explicit-retrieval-20261016/runtime-intake/source-review-pending-01.json`.
These additions are executable task oracles, with review flags still false.
Prior two-case public/native measurements retain their original suite/grader
identities. They are not current four-case qualification. Do not update a report
identity to make old evidence current.

Use the existing materializer with the SQLAlchemy checkout and this `suite.json`.
The initial local exact source map is
`.hashmarks/backend-e2e/explicit-retrieval-20261016/runtime-intake/debug-sources.json`.
Regenerate a runtime specimen with `python -m
scripts.repository_evaluation.capture_backend_failure --suite .../debug/suite.json
--sources-file ... --workflow WORKFLOW --output-dir NEW`; use the required
Python 3.14 interpreter for the forward-reference case. Freeze the resulting
source-only runtime oracle and preserve the original captures before updating
catalog identities. The current captures and admission report are under
`.hashmarks/backend-e2e/explicit-retrieval-20261016/runtime-captures-02/`.
Acquire public measurements with `run_backend --suite .../debug/suite.json
--sources-file ... --output-dir NEW`. Acquire native specimens with
`run_backend_native`, the same suite/source map, `--regenerate`, a new capture
root and a new report directory. A native PASS covers only its nominated source
bindings and transports; the twenty-row campaign still needs complete breadth,
independent review, required witness membership and final validation.
