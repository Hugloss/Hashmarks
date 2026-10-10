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
