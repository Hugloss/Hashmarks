# Post-#415 repository evidence checkpoint ledger

**Original baseline:** merged #415 (`f4c18cfb05891505cbf8b8377b729ff03cb9abca`); follow-on work now builds on merged #416 (`c7a2b05986410c4e9ac8ceb6a4d4ed8c20d18f70`). This is a follow-on to the historical single-PR
H01–H16 admission plan, not a claim that every conditional item in that
historical plan shipped.

## Current cohesive implementation bundle

| Checkpoint | Classification | Implementation / proof boundary |
| --- | --- | --- |
| H09a | EXTEND_EXISTING_OWNER | Explicitly selected Python route/tool handler literal dictionary-return syntax, each return site separately anchored to canonical repository evidence; dynamic/unpacking stays unknown |
| H09b | EXTEND_EXISTING_OWNER | Handler-local `name["key"]` access syntax, with source location and syntactic receiver; no owner alias analysis or producer-consumer matching |
| H10a | ALREADY_PRESENT + SOURCE EVIDENCE | Existing route-to-handler decorator declaration is the only scoped association; body-syntax observations live on that declaration, not an inferred call graph or impact classification |
| H16a | REGRESSION | Default unchanged; denied, stale, oversized, nested, unknown and replay cases cannot imply complete coverage or compatible API shape |

The additional handler capture is **opt-in** and uses the
`StaticPythonInterfaceDeclarations` provider, already bound by CodeMap's
repository-declaration discovery. There is no new MCP tool, index, service,
cache, LSP process or historical authority.

## H06 follow-on checkpoint bundle

| Checkpoint | Classification | Implementation / proof boundary |
| --- | --- | --- |
| H06a | EXTEND_EXISTING_OWNER | Explicit caller-supplied LSP `textDocument/hover` capture, existing source-binding and generation authority; zero relationship claims |
| H06b | REGRESSION | Bounded modern/legacy hover forms, nullable/error states, strict unknown/dynamic semantics, malformed and oversized capture rejection |
| H06c | REGRESSION | Rehashed packet forgery cannot assert relationship edges, trusted semantics or negative evidence from hover |
| H06d | PRESENTATION/DOCS | Existing native/presentation parity, documentation and source-revision contract; no new MCP method or agent-harness behavior |

H06 document-symbol captures remain conditional: their different request shape
and scope cannot be forced into cursor-bound relationship queries without an
explicit non-edge ownership plan.

## Backend B01–B05 bundle (H04 exact range closure)

| Checkpoint | Decision | Authority |
| --- | --- | --- |
| B01 owner | Reuse | `task_evidence` + existing `change_impact.surfaces` |
| B02 relationships | Reuse + exact locator | Current direct SCIP/LSP/structural evidence; overlap supplies exact query arguments, never graph edges |
| B03 changed-line to symbol | Extend existing owner | Caller-reported range + source-revision-bound indexed symbol overlap, bounded and opt-in |
| B04 verification | Reuse | Existing verification surfaces; no test coverage inferred from overlaps |
| B05 after-change | Reuse | Existing `post_change` ownership/freshness/semantic invalidation/delta |
| B01–B05 regressions | Add | No default drift, denied/stale/malformed/overflow fail-safe, MCP/CLI and presentation parity |

No global graph, runtime execution, second source authority, new MCP tool,
new search/indexer, history engine or agent workflow is admitted. A future
more-precise line-level *edit* oracle must be producer-supplied with revision
binding and separate qualification; reported spans alone prove no actual edit.

## B06 backend decorator source correspondence (following merged #419)

The changed-line B03 index-range query intentionally starts at a Python
function/class declaration line. A changed `@router.get`, `@app.post`,
`@mcp.tool`, or other decorator above the declaration is therefore **not**
an indexed-symbol-range overlap. This reproducible backend handler locality
gap must not be repaired by pretending the symbol starts earlier.

B06 extends the existing optional `changed_line_evidence` packet with a
**separate direct syntax observation** for current Python source only.
It parses at most 256 KiB of already source-admitted bytes per span, finds
decorator expressions that directly overlap reported lines and binds each to
an exact current indexed function, method or class at its declaration line.
A bounded query must establish unique source/index correspondence; otherwise
the association is unresolved and never promoted to a selected owner.
At most 16 associations are retained per span with explicit omission and
unresolved counts. Only unchanged source revisions survive the existing
read-after-query qualification.

The handler/decorator association is **syntactic**, not runtime route
registration, call graph connectivity, affected execution, verification
coverage or evidence of a real edit. Ordinary symbol overlaps remain
unchanged. No new index/schema/MCP tool/state owner, workflow, or source
scanner is admitted; non-Python files retain their prior output.

## Backend B07–B10: qualified decorator context (after #420)

The B06 change-line association supplies an exact handler target for a directly
overlapping decorator, but not the syntax of adjacent declarations on the
same handler. A backend agent changing `@auth.required` could still need
another exploratory source read to see that `@router.get(...)` is adjacent.
This bundle adds direct syntax within the existing request-local B06 producer:

- **B07 – direct callee:** attribute or name syntax of selected decorators,
  with explicit `dynamic-or-unsupported` for chained/unknown expressions;
  no framework/route registration classification.
- **B08 – locality:** identify which decorator ranges overlap the caller's
  changed span versus other syntactically adjacent decorators on that same
  exact indexed declaration. Edited decorators take retention precedence,
  then rows are rendered in source order.
- **B09 – bounded literal argument facts:** preserve first positional string
  and named `path`/`name` string syntax independently; expanded argument
  syntax and unknown/over-bound string values cannot become route truth.
  Up to six decorator observations per handler and 128 characters per
  retained literal. Caller-supplied changed spans remain bounded by B03.
- **B10 – evidence and privacy:** admit decorator call syntax only for the
  canonical `source` visibility level; `outline` does not expose literal
  arguments. Preserve the existing second member-revision read, truncation,
  independent uncertainty, default change-impact output and exact
  repository-intelligence-only product boundary.

This is not a runtime API catalog, route resolver, or graph search. The
original indexed symbol location is unchanged. The existing optional MCP
`change_impact(changed_line_spans=...)` transports these observations;
there is no new public tool or persistent schema.

## Backend B11–B14: direct indexed handler body context (after #421)

B06–B10 established an exact source/index association and bounded decorator
call syntax for a caller-reported changed decorator. The existing selected
`StaticPythonInterfaceDeclarations` producer already directly extracts
literal dictionary-return sites and handler-local literal subscript accesses,
but those facts are not in the changed-line packet. Repeated exploratory
source reads are therefore still needed to inspect basic handler response and
access syntax after a decorator edit.

This bundle **reuses that exact handler-body extractor** (no second AST
semantics owner) within the existing request-local decorator association:

- **B11:** retain an exact, bounded indexed declaration signature and attach
  the direct function-body syntax to the already-qualified indexed handler;
  classes are explicitly not function-body evidence.
- **B12:** distinguish independently ordered literal dictionary-return sites
  from `unresolved-return` sites and handler-local `name["key"]` syntax;
  nested scopes are not attributed to the outer handler. Up to eight sites
  of each kind are retained with observed and omitted counts.
- **B13:** every body observation remains incomplete direct static syntax,
  with runtime response shape unknown, cross-artifact correspondence
  unresolved, and negative evidence inadmissible. The shared extractor's
  overflow causes a local unresolved body state, not a failed change-impact
  operation or a false empty body.
- **B14:** reuse CodeMap's source visibility and second stable revision read;
  never show handler source values on outline/deny paths. Verify equality
  with the opt-in declaration provider and exact current-source MCP replay
  after an edit.

No route runtime, typed API compatibility, consumer schema matching,
verification selection, new public tool, durable state or semantic graph is
introduced. No `changed_line_spans` means the old result is unchanged.

## Backend B15–B19: qualified handler input boundary (after merged #422)

| Checkpoint | Admitted change | Authority and unknowns |
| --- | --- | --- |
| B15 | Positional/keyword parameter declarations with exact indexed handler and signature site | Shared Python AST, <=16 per selected handler; no runtime signature binding |
| B16 | Bounded direct annotations and declared return annotation | Current admitted source only; no inferred Pydantic schema or API response |
| B17 | Constant default *kinds* and direct default-call/keyword syntax | No literal default values, evaluation or dependency resolution |
| B18 | Bounded `Annotated` metadata call sites with omissions | No framework-specific DI engine, validation or transitive provider graph |
| B19 | Shared provider/change-impact extractor, source privacy, adversarial regressions | Default provider unchanged, no added MCP tool, no consumer compatibility claim |

The implementation has one bounded `handler_input_syntax` AST owner. The
existing explicit `StaticPythonInterfaceDeclarations` path opts in
independently of body syntax. A current, uniquely indexed changed-decorator
association exposes that exact same syntax via the existing
`change_impact` source-bound packet. Both remain observations, not runtime
contracts or tests executed. Producer-consumer correspondence, config binding
and dependency transition facts continue with their *existing separate*
declaration/dependency authorities; names alone are never joined.

## Backend B20–B24: selected schema and configuration syntax

Build upon merged #425 without repeating the B06–B19 observations.
The new `StaticPythonBackendDeclarations` is caller-selected and routes
through the existing qualified `RepositoryDeclarationProviderContext`:

| Checkpoint | Direct fact | Explicit non-claim |
| --- | --- | --- |
| B20 | Selected-file top-level `BaseModel` / `BaseSettings` class-base syntax | Resolved class/framework identity |
| B21 | Class-local field annotation and `Field(...)` call syntax | Pydantic validation, requiredness, default values |
| B22 | Exact `os.getenv` / `os.environ` key and direct assignment syntax | Runtime `os` binding, precedence or actual config values |
| B23 | Bounded sources, fields, groups, paths and provider revision checks | Exhaustive absence or scanned repository universe |
| B24 | Independent provider switches, adversarial tests, documentation and original declaration owner | Producer/consumer compatibility or inferred cross-file edges |

This is one PR and one explicit provider. C01–C04 producer/consumer syntax
work in the separate, unmerged #424 is not incorporated or duplicated.
No call graph, new MCP method, runtime framework analyzer, Pydantic loader,
configuration evaluator or semantic inference is introduced.

## Backend B25–B29: exact source-local schema/config correspondence

Based on merged #426 and #423. Do not overlap the still-open,
separately qualified #424 C01–C04 producer/consumer provider.

| Checkpoint | Admitted observation | Explicit boundary |
| --- | --- | --- |
| B25 | Separate load/store/delete target syntax of `os.environ[...]` | Does not execute or claim actual reads/writes |
| B26 | An annotated model field's exact RHS is a directly observed env expression, with the same line/column site | No inferred default-factory, config binding or cross-file match |
| B27 | Competing positional and keyword arguments are ambiguous, expansions unresolved | No first-value-wins argument binding |
| B28 | Source visibility, revision replay, omitted/default value privacy and tests | No stale or denied evidence promotion |
| B29 | Existing explicit provider, independent modes and presentation parity | No new MCP tools, backend resolver or runtime schema contract |

Reuse the existing `_env_site` observation owner for both environmental
site declarations and field-local initializer evidence. Match on **AST node
identity in the same admitted parse**, never lexical name similarity. Remain
`correspondence=unresolved`, `coverage=incomplete`,
`negative_evidence_admissible=false`. Exact owner/policy contract continues
to be the repository-declaration provider context. No Python code execution.

## Cross-artifact C01–C04: caller-nominated producer/consumer syntax pairs (after #422)

- **C01 — explicit pairing only:** one caller-selected provider accepts at most
  16 five-field nominations
  `(producer_path, producer_function, consumer_path, consumer_function, receiver)`.
  Both paths must already be in its explicit, bounded source path selection;
  both functions must be unique top-level Python declarations. The producer
  must have a directly observed supported route/MCP tool decorator. Duplicates,
  missing/renamed paths or functions, and unsupported decorator syntax are
  labelled unresolved in provider provenance, not claimed absent.
- **C02 — existing body syntax owner:** producer returns and consumer literal
  `receiver["key"]` read sites come from the existing source-bound
  `_handler_body_syntax` extractor; nested functions and aliases are excluded.
  A single captured module AST is reused for both producer discovery and
  pair extraction when opted in. No second source scan, parser or graph owner.
- **C03 — independent authority:** one repository-declaration group contains
  separately bound producer and consumer syntax observations with explicit
  provenance. `correspondence=unresolved`, `coverage=incomplete`,
  `comparison=ambiguous`, runtime binding/shape unknown and absence unknown
  even when observed keys differ. Pair nomination does not prove a call chain,
  API compatibility, missing field, runtime response or downstream impact.
- **C04 — compatibility/qualification:** the empty default remains identical;
  invalid nomination fails before repository reads, 16-site syntax overflow
  fails closed, exact source bindings and revision changes use the existing
  declaration observer, and projection must preserve the same facts.
  Focused negative/changed-source/ordering/duplicate tests are required.

No new MCP tool, ambient provider, executable parser, global graph, ranker,
test runner or source-of-truth precedence is admitted.

## Backend B30–B34: source-bound evidence readiness and next-read guidance

Continue from merged #427 and #424, **without duplicating** the
C01–C04 producer/consumer pair provider or guessing runtime behavior.

| Checkpoint | Implementation | Hard constraint |
| --- | --- | --- |
| B30 | Opt-in direct-syntax vs runtime-unresolved status | Empty read list never proves complete runtime scope |
| B31 | Existing observed source ranges mapped to exact read requests | No new filesystem scanning, graph, owner or tool |
| B32 | Suppress redundant source reads when literal lookup syntax is already known | Literal syntax does not prove actual env binding |
| B33 | Max eight bounded reads with observed/retained/omitted counts | Truncation can never admit negative evidence |
| B34 | Strict boolean opt-in, revision/privacy/default parity regressions, docs | Source binding remains provider-owned |

Read guidance is a **pure projection from existing declaration observations**.
It does not inspect files, discover dependencies, choose edits/tests, execute
tools or prove runtime API compatibility. The producer/consumer work merged in
#424 remains under its separate source-declaration authority.

## Backend B35–B39: frozen external evaluation of navigation

After merged #428, first prove a controlled evidence presentation
intervention before claiming an agent uplift. The Hashmarks evaluation-only
exporter `scripts.agent_evaluation.backend_navigation_ablation` freezes
two explicitly selected backend observations per case under one source
snapshot and the same semantic owner.

| Checkpoint | Evidence | Non-claim |
| --- | --- | --- |
| B35 | Bounded caller-selected task and path manifest | No automatic task/oracle generation |
| B36 | Same CodeMap and matching provider input revisions for paired arms | No externally attested host workspace |
| B37 | Exact source-fact equivalence after removing only opt-in navigation | Not Hashmarks versus bare |
| B38 | Canonical size, SHA-256 observation and export identities with self-consistency validation | Not signed provenance, host capture or cryptographic anti-forgery |
| B39 | Explicit exposure, visibility, usage and outcome unknowns; adversarial regressions and handoff docs | No agent benefit before agentsCookbook host trials |

Next independent agentsCookbook work: run paired native coding-agent
tasks with host-attested delivery, correct source-version binding, controlled
arm order, identical tool catalog, actual model-visible evidence identity,
independent task success, first-choice/late-rescue attribution, native
reads and verified patch outcomes. **Do not** infer agent understanding
or a PASS from export sizes or a navigation recommendation alone.

## Open conditional checkpoints

- **H04:** changed-line → symbol/relationship claims require a direct
  revision-bound source/range oracle and a demonstrated gap in existing
  repository delta/change-impact/structural-locality. No inferred impact.
- **H06 remaining:** document-symbol or other LSP observations require exact
  producer scopes and protocol validation; do not force symbol lists into the
  hover/relationship edge owner.
- **H09 (remaining):** a future explicit provider may attest normalized
  producer/consumer field correspondence; without attributable evidence no
  mismatch, breaking-change or absence judgment is admitted.
- **H10 (remaining):** route-local direct evidence composition may be added
  only with qualified endpoints; no transitive downstream API impact.
- **H11:** process membership is provider-only and has no current proved
  direct producer corpus. Do not infer a process graph from static naming.
- **H12/H14/H15:** compare real retrieval, catalog and projection measurements
  in agentsCookbook/host trials before changing ranking, tools, presentation
  or transport. Preserve rare-owner recall and exact model-visible attribution.

## Qualification gates for this follow-up

1. Exact default discovery identity and output remains unchanged without opt-in.
2. Both literal and unresolved sites are preserved without inferring complete
   response/consumer coverage or runtime contract compatibility.
3. Literal facts require current, admitted, source-bound evidence. Denied and
   changed inputs fail closed; malformed boolean and site overflow reject.
4. Native declaration deltas and existing evidence presentation remain sourced
   from their existing semantic owners.
5. Python 3.11/3.14, Ruff/formatting, full MCP, wheel and release qualification
   must be checked on the exact PR head. An unrun gate is **not** PASS.
